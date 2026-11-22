"""آزمایشگاه شبیه‌سازی پژوهش — دیتاست، کاوش متغیرها، ارتباط متغیرها و شبیه‌سازی مدل‌ها.

چرخهٔ کامل دیتاساینس درون سامانه:
۱) بارگذاری دیتاست (CSV/XLSX) با تشخیص خودکار نوع ستون‌ها و پیوند به پروژه/سند پژوهش
۲) کاوش: پروفایل توصیفی، توزیع‌ها، همبستگی پیرسون/اسپیرمن، پراکندگی، کای‌دو، ANOVA
۳) شبیه‌سازی: رگرسیون (خطی/ریج/لاسو/چندجمله‌ای/درخت/جنگل/KNN)، طبقه‌بندی
   (لجستیک/درخت/جنگل/KNN/بیز ساده) و خوشه‌بندی (K-Means/سلسله‌مراتبی/DBSCAN)
۴) ثبت آزمایش‌ها با پارامترها و نتایج برای مقایسه و بازتولید، پیش‌بینی تک‌ردیفی،
   و درج خودکار خلاصهٔ نتایج در بخش «یافته‌ها»ی سند پژوهش تیمی.
"""
import csv
import io
import re
from collections import Counter

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_roles
from ..core.database import get_db
from ..core.utils import log_event, now_utc
from ..models import LabDataset, LabExperiment, User

router = APIRouter(prefix="/api/v1/lab", tags=["آزمایشگاه شبیه‌سازی"])

# ---------- سقف‌های ورودی (دیتاست پژوهشی معمولاً کوچک است) ----------
MAX_UPLOAD_BYTES = 5 * 1024 * 1024      # ۵ مگابایت
MAX_ROWS = 10_000
MAX_COLS = 200
MAX_ONEHOT_COLS = 400                    # سقف ستون‌های ساختگی پس از کدگذاری مقوله‌ای
TOP_CATEGORIES = 12                      # بیشینهٔ مقوله‌های یک ستون؛ بقیه در «سایر»
SAMPLE_SCATTER = 800                     # سقف نقاط نمودار پراکندگی
SAMPLE_PRED_ACTUAL = 500                 # سقف نقاط «واقعی-پیش‌بینی»

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "—", "missing", "؟", "?"}

REGRESSION_MODELS = {
    "linear": "رگرسیون خطی چندگانه",
    "ridge": "رگرسیون ریج (L2)",
    "lasso": "رگرسیون لاسو (L1)",
    "poly2": "رگرسیون چندجمله‌ای (درجهٔ ۲)",
    "tree": "درخت تصمیم رگرسیون",
    "forest": "جنگل تصادفی رگرسیون",
    "knn": "نزدیک‌ترین همسایه‌ها (KNN رگرسیون)",
}
CLASSIFICATION_MODELS = {
    "logistic": "رگرسیون لجستیک",
    "tree": "درخت تصمیم طبقه‌بندی",
    "forest": "جنگل تصادفی طبقه‌بندی",
    "knn": "نزدیک‌ترین همسایه‌ها (KNN)",
    "nb": "بیز ساده گاوسی",
}
CLUSTERING_MODELS = {
    "kmeans": "خوشه‌بندی K-Means",
    "hierarchical": "خوشه‌بندی سلسله‌مراتبی (تجمیعی)",
    "dbscan": "خوشه‌بندی DBSCAN (چگالی‌محور)",
}
TASKS = {
    "regression": {"title": "رگرسیون (پیش‌بینی مقدار عددی)", "models": REGRESSION_MODELS},
    "classification": {"title": "طبقه‌بندی (پیش‌بینی رده)", "models": CLASSIFICATION_MODELS},
    "clustering": {"title": "خوشه‌بندی (کشف گروه‌ها)", "models": CLUSTERING_MODELS},
}


# ============================================================
# ابزارهای عمومی
# ============================================================

def _py(x):
    """تبدیل انواع numpy به نوع پایتون برای JSON."""
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        v = float(x)
        return None if np.isnan(v) else v
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def _f(x, nd=4):
    """گرد کردن امن برای JSON."""
    if x is None:
        return None
    try:
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return None
        return round(v, nd)
    except (TypeError, ValueError):
        return None


_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm_cell(v):
    """نرمال‌سازی سلول خام: ارقام فارسی، فاصله، نشانه‌های گمشده."""
    if v is None:
        return None
    s = str(v).strip().translate(_FA_DIGITS)
    if s.lower() in MISSING_TOKENS:
        return None
    return s


def _try_float(s):
    if s is None:
        return None
    try:
        return float(str(s).replace(",", ""))   # جداکنندهٔ هزارگان حذف می‌شود
    except (TypeError, ValueError):
        return None


def _detect_and_convert(header, raw_rows):
    """تشخیص نوع ستون‌ها (numeric | categorical) و تبدیل مقادیر؛ خروجی: rows و meta."""
    n_cols = len(header)
    cells = [[_norm_cell(r[i]) if i < len(r) else None for i in range(n_cols)] for r in raw_rows]
    meta, rows = [], []
    for j, name in enumerate(header):
        vals = [c[j] for c in cells]
        non_null = [v for v in vals if v is not None]
        floats = [_try_float(v) for v in non_null]
        ok = sum(1 for f in floats if f is not None)
        is_numeric = bool(non_null) and ok / len(non_null) >= 0.8
        meta.append({"name": name, "dtype": "numeric" if is_numeric else "categorical",
                     "n_missing": len(vals) - len(non_null)})
    for c in cells:
        row = {}
        for j, m in enumerate(meta):
            v = c[j]
            row[m["name"]] = _try_float(v) if (m["dtype"] == "numeric" and v is not None) else v
        rows.append(row)
    # شمارش مقدار یکتا برای متادیتا
    for j, m in enumerate(meta):
        if m["dtype"] != "numeric":
            vals = {c[j] for c in cells if c[j] is not None}
            m["n_unique"] = len(vals)
        else:
            m["n_unique"] = None
    return rows, meta


def _dedupe(names):
    seen, out = set(), []
    for n in names:
        n = (n or "").strip() or "ستون"
        base, k = n, 2
        while n in seen:
            n = f"{base}_{k}"
            k += 1
        seen.add(n)
        out.append(n)
    return out


def _decode_bytes(b: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise HTTPException(status_code=400, detail="رمزگذاری فایل قابل تشخیص نبود (UTF-8 ذخیره کنید)")


def _parse_csv(b: bytes):
    text = _decode_bytes(b)
    first = text.splitlines()[0] if text.splitlines() else ""
    delim = max([",", ";", "\t", "|"], key=lambda d: first.count(d))
    reader = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    reader = [r for r in reader if any((x or "").strip() for x in r)]
    if len(reader) < 3:
        raise HTTPException(status_code=400, detail="فایل باید حداقل سرستون و دو ردیف داده داشته باشد")
    header = _dedupe(reader[0])
    rows, meta = _detect_and_convert(header, reader[1:])
    return rows, meta


def _parse_xlsx(b: bytes):
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=400, detail="پشتیبانی Excel فعال نیست")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        grid = [list(r) for r in ws.iter_rows(values_only=True)]
        grid = [r for r in grid if any((x is not None and str(x).strip()) for x in r)]
        if len(grid) < 3:
            raise HTTPException(status_code=400, detail="برگهٔ Excel باید حداقل سرستون و دو ردیف داده داشته باشد")
        header = _dedupe([str(x) if x is not None else "" for x in grid[0]])
        rows, meta = _detect_and_convert(header, grid[1:])
        return rows, meta
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"خواندن فایل Excel ناموفق بود: {e}")


def _get_dataset_checked(db: Session, ds_id: int, user: User) -> LabDataset:
    d = db.get(LabDataset, ds_id)
    if not d:
        raise HTTPException(status_code=404, detail="دیتاست یافت نشد")
    if d.owner_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط صاحب دیتاست یا مدیر به آن دسترسی دارد")
    return d


def _ser_dataset(d: LabDataset, with_meta=True):
    return {"id": d.id, "title": d.title, "description": d.description, "filename": d.filename,
            "size": d.size, "n_rows": d.n_rows, "n_cols": d.n_cols,
            "columns_meta": d.columns_meta or [], "project_id": d.project_id,
            "research_doc_id": d.research_doc_id,
            "created_at": d.created_at.isoformat() if d.created_at else None}


def _ser_experiment(e: LabExperiment, with_artifacts=True):
    out = {"id": e.id, "dataset_id": e.dataset_id, "title": e.title, "task": e.task,
           "task_fa": TASKS.get(e.task, {}).get("title", e.task), "model": e.model,
           "model_fa": e.model_fa, "target": e.target, "features": e.features or [],
           "params": e.params or {}, "metrics": e.metrics or {}, "status": e.status,
           "error": e.error, "created_at": e.created_at.isoformat() if e.created_at else None}
    if with_artifacts:
        out["artifacts"] = e.artifacts or {}
    return out


# ============================================================
# کدگذاری ویژگی‌ها — عددی با جای‌گذاری میانگین، مقوله‌ای با One-Hot
# (بدون pandas؛ برای دیتاست‌های کوچک پژوهشی دقیق و شفاف)
# ============================================================

def _encode_matrix(rows, features, columns_meta, target=None, task=None):
    """ماتریس ویژگی + هدف می‌سازد؛ خروجی شامل فرادادهٔ کدگذاری برای پیش‌بینی تک‌ردیفی."""
    meta = {c["name"]: c for c in columns_meta}
    for f in features:
        if f not in meta:
            raise HTTPException(status_code=400, detail=f"ستون «{f}» در دیتاست نیست")
    numeric_cols = [f for f in features if meta[f]["dtype"] == "numeric"]
    cat_cols = [f for f in features if meta[f]["dtype"] != "numeric"]
    if task == "clustering" and cat_cols:
        raise HTTPException(status_code=400,
                            detail="برای خوشه‌بندی فقط ستون‌های عددی را انتخاب کنید (کدگذاری مقوله‌ای در خوشه‌بندی تفسیرپذیر نیست)")

    # ردیف‌های با هدف گمشده حذف می‌شوند
    keep = np.ones(len(rows), dtype=bool)
    y = None
    if task in ("regression", "classification") and target:
        if target not in meta:
            raise HTTPException(status_code=400, detail=f"ستون هدف «{target}» در دیتاست نیست")
        if task == "regression" and meta[target]["dtype"] != "numeric":
            raise HTTPException(status_code=400, detail="ستون هدف رگرسیون باید عددی باشد؛ برای رده‌ها از طبقه‌بندی استفاده کنید")
        tvals = [r.get(target) for r in rows]
        if task == "regression":
            y = np.array([v if isinstance(v, (int, float)) else np.nan for v in tvals])
            keep &= ~np.isnan(y)
        else:
            y_raw = [None if v is None else str(v) for v in tvals]
            keep &= np.array([v is not None for v in y_raw])
    if keep.sum() < 3:
        raise HTTPException(status_code=400, detail="پس از حذف ردیف‌های با مقدار هدف گمشده، دادهٔ کافی برای آموزش نیست")

    idx = np.where(keep)[0]
    sub = [rows[i] for i in idx]

    # ماتریس عددی + جای‌گذاری میانگین
    Xn = np.full((len(sub), len(numeric_cols)), np.nan, dtype=float)
    for j, c in enumerate(numeric_cols):
        for i, r in enumerate(sub):
            v = r.get(c)
            if isinstance(v, (int, float)):
                Xn[i, j] = float(v)
    means = {}
    for j, c in enumerate(numeric_cols):
        col = Xn[:, j]
        mu = float(np.nanmean(col)) if np.isfinite(col).any() else 0.0
        means[c] = mu
        col[np.isnan(col)] = mu

    # کدگذاری مقوله‌ای: مقوله‌های پرتکرار + «سایر» + «گمشده»
    cat_maps, Xc_parts, onehot_names = {}, [], []
    for c in cat_cols:
        counts = Counter(str(r.get(c)) for r in sub if r.get(c) is not None)
        top = [k for k, _ in counts.most_common(TOP_CATEGORIES)]
        cmap = {k: i for i, k in enumerate(top)}
        cat_maps[c] = cmap
        n_bucket = len(top) + 1  # + سایر/گمشده
        M = np.zeros((len(sub), n_bucket))
        for i, r in enumerate(sub):
            v = r.get(c)
            if v is None:
                M[i, len(top)] = 1.0          # ستون آخر: گمشده/سایر
            else:
                M[i, cmap.get(str(v), len(top))] = 1.0
        Xc_parts.append(M)
        onehot_names += [f"{c}={k}" for k in top] + [f"{c}(سایر/گمشده)"]

    X = np.hstack([Xn] + Xc_parts) if Xc_parts else Xn
    feat_names = numeric_cols + onehot_names
    if X.shape[1] > MAX_ONEHOT_COLS:
        raise HTTPException(status_code=400,
                            detail=f"پس از کدگذاری مقوله‌ای {X.shape[1]} ستون ساخته می‌شود (بیشتر از {MAX_ONEHOT_COLS})؛ "
                                   "ستون‌های مقوله‌ای با مقوله‌های زیاد را کنار بگذارید")

    if task == "classification":
        labels = sorted({str(v) for v in (y_raw[i] for i in idx)})
        lmap = {l: i for i, l in enumerate(labels)}
        y = np.array([lmap[str(y_raw[i])] for i in idx])
        target_meta = {"labels": labels}
    elif task == "regression":
        y = y[idx]
        target_meta = {}
    else:
        target_meta = {}
    return {"X": X, "y": y, "feat_names": feat_names, "numeric_cols": numeric_cols,
            "cat_maps": cat_maps, "means": means, "idx": idx, "target_meta": target_meta}


def _encode_one(rows_one, features, columns_meta, enc):
    """کدگذاری یک ردیف برای پیش‌بینی — با همان نقشهٔ میانگین‌ها و مقوله‌های آموزش."""
    meta = {c["name"]: c for c in columns_meta}
    numeric_cols = [f for f in features if meta[f]["dtype"] == "numeric"]
    cat_cols = [f for f in features if meta[f]["dtype"] != "numeric"]
    xn = np.zeros((1, len(numeric_cols)), dtype=float)
    for j, c in enumerate(numeric_cols):
        v = rows_one.get(c)
        parsed = _try_float(_norm_cell(v)) if v is not None else None
        xn[0, j] = parsed if parsed is not None else enc["means"].get(c, 0.0)
    parts = [xn]
    for c in cat_cols:
        cmap = enc["cat_maps"].get(c, {})
        n_bucket = len(cmap) + 1
        M = np.zeros((1, n_bucket))
        v = rows_one.get(c)
        if v is None:
            M[0, len(cmap)] = 1.0
        else:
            M[0, cmap.get(str(_norm_cell(v)), len(cmap))] = 1.0
        parts.append(M)
    return np.hstack(parts)


# ============================================================
# اجرای مدل‌ها
# ============================================================

def _split(X, y, params, task, labels=None):
    from sklearn.model_selection import train_test_split
    test_size = float(params.get("test_size", 0.25))
    test_size = min(max(test_size, 0.1), 0.5)
    seed = int(params.get("random_state", 42))
    stratify = None
    if task == "classification" and labels is not None and len(labels) > 1:
        counts = Counter(y.tolist())
        if min(counts.values()) >= 2 and int(len(y) * test_size) >= len(labels):
            stratify = y
    return train_test_split(X, y, test_size=test_size, random_state=seed, stratify=stratify)


def _ip(params, key, default):
    """پارامتر عدد صحیح امن — مقدار None/خالی به پیش‌فرض برمی‌گردد."""
    v = params.get(key)
    try:
        return int(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _fp(params, key, default):
    """پارامتر عدد اعشاری امن."""
    v = params.get(key)
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _regressor(model_key, params):
    from sklearn.linear_model import LinearRegression, Ridge, Lasso
    from sklearn.tree import DecisionTreeRegressor
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import PolynomialFeatures
    seed = int(params.get("random_state", 42))
    if model_key == "linear":
        return LinearRegression()
    if model_key == "ridge":
        return Ridge(alpha=_fp(params, "alpha", 1.0))
    if model_key == "lasso":
        return Lasso(alpha=_fp(params, "alpha", 0.1), max_iter=20000)
    if model_key == "poly2":
        return Pipeline([("poly", PolynomialFeatures(degree=2, include_bias=False)),
                         ("lin", LinearRegression())])
    if model_key == "tree":
        return DecisionTreeRegressor(max_depth=_ip(params, "max_depth", 6) or None, random_state=seed)
    if model_key == "forest":
        return RandomForestRegressor(n_estimators=_ip(params, "n_estimators", 100), random_state=seed,
                                     n_jobs=1)
    if model_key == "knn":
        return KNeighborsRegressor(n_neighbors=_ip(params, "k", 5))
    raise HTTPException(status_code=400, detail="مدل رگرسیون نامعتبر است")


def _classifier(model_key, params):
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.naive_bayes import GaussianNB
    seed = int(params.get("random_state", 42))
    if model_key == "logistic":
        return LogisticRegression(max_iter=2000)
    if model_key == "tree":
        return DecisionTreeClassifier(max_depth=_ip(params, "max_depth", 6) or None, random_state=seed)
    if model_key == "forest":
        return RandomForestClassifier(n_estimators=_ip(params, "n_estimators", 100), random_state=seed, n_jobs=1)
    if model_key == "knn":
        return KNeighborsClassifier(n_neighbors=_ip(params, "k", 5))
    if model_key == "nb":
        return GaussianNB()
    raise HTTPException(status_code=400, detail="مدل طبقه‌بندی نامعتبر است")


def _histogram(vals, bins=25):
    v = np.asarray([x for x in vals if x is not None], dtype=float)
    if v.size == 0:
        return {"edges": [], "counts": []}
    counts, edges = np.histogram(v, bins=min(bins, max(5, v.size // 2)))
    return {"edges": [_f(e) for e in edges], "counts": [int(c) for c in counts]}


def _downsample_pairs(pairs, cap):
    if len(pairs) <= cap:
        return pairs
    step = len(pairs) / cap
    return [pairs[int(i * step)] for i in range(cap)]


def _run_regression(model_key, enc, params):
    from sklearn import metrics as M
    X, y, names = enc["X"], enc["y"], enc["feat_names"]
    Xtr, Xte, ytr, yte = _split(X, y, params, "regression")
    mdl = _regressor(model_key, params)
    mdl.fit(Xtr, ytr)
    ptr, pte = mdl.predict(Xtr), mdl.predict(Xte)
    nz = yte != 0
    mape = float(np.mean(np.abs((yte[nz] - pte[nz]) / yte[nz])) * 100) if nz.any() else None
    metrics = {
        "r2_train": _f(M.r2_score(ytr, ptr)), "r2_test": _f(M.r2_score(yte, pte)),
        "mae_test": _f(M.mean_absolute_error(yte, pte)),
        "rmse_test": _f(float(np.sqrt(M.mean_squared_error(yte, pte)))),
        "mape_test": _f(mape, 2),
        "n_train": int(len(ytr)), "n_test": int(len(yte)),
    }
    # جدول ضرایب یا اهمیت ویژگی‌ها
    coef = []
    try:
        if model_key == "poly2":
            pnames = list(mdl.named_steps["poly"].get_feature_names_out(names))[:40]
            vals = mdl.named_steps["lin"].coef_[:len(pnames)]
            coef = [{"feature": n, "value": _f(v)} for n, v in zip(pnames, vals)]
        elif hasattr(mdl, "coef_"):
            vals = np.ravel(mdl.coef_)
            coef = [{"feature": n, "value": _f(v)} for n, v in zip(names, vals)]
        elif hasattr(mdl, "feature_importances_"):
            coef = [{"feature": n, "value": _f(v)} for n, v in zip(names, mdl.feature_importances_)]
        coef = sorted(coef, key=lambda d: -abs(d["value"] or 0))[:20]
    except Exception:
        pass
    pairs = [{"actual": _f(a), "predicted": _f(p)} for a, p in zip(yte, pte)]
    pairs = _downsample_pairs(pairs, SAMPLE_PRED_ACTUAL)
    residuals = (yte - pte).tolist()
    artifacts = {
        "pred_actual": pairs,
        "residual_hist": _histogram(residuals),
        "coefficients": coef,
        "equation_note": f"تعداد ویژگی‌های مؤثر پس از کدگذاری: {len(names)}",
    }
    return metrics, artifacts


def _run_classification(model_key, enc, params):
    from sklearn import metrics as M
    X, y, names = enc["X"], enc["y"], enc["feat_names"]
    labels = enc["target_meta"]["labels"]
    Xtr, Xte, ytr, yte = _split(X, y, params, "classification", labels=labels)
    mdl = _classifier(model_key, params)
    mdl.fit(Xtr, ytr)
    ptr, pte = mdl.predict(Xtr), mdl.predict(Xte)
    prec, rec, f1, sup = M.precision_recall_fscore_support(yte, pte, labels=range(len(labels)),
                                                           zero_division=0)
    cm = M.confusion_matrix(yte, pte, labels=range(len(labels)))
    metrics = {
        "accuracy_train": _f(M.accuracy_score(ytr, ptr)), "accuracy_test": _f(M.accuracy_score(yte, pte)),
        "balanced_accuracy_test": _f(M.balanced_accuracy_score(yte, pte)),
        "f1_macro_test": _f(M.f1_score(yte, pte, average="macro", zero_division=0)),
        "n_train": int(len(ytr)), "n_test": int(len(yte)), "classes": labels,
    }
    artifacts = {
        "confusion": {"labels": labels, "matrix": [[int(v) for v in row] for row in cm]},
        "per_class": [{"label": labels[i], "precision": _f(prec[i]), "recall": _f(rec[i]),
                       "f1": _f(f1[i]), "support": int(sup[i])} for i in range(len(labels))],
    }
    # اهمیت ویژگی / ضرایب
    coef = []
    try:
        if hasattr(mdl, "feature_importances_"):
            coef = [{"feature": n, "value": _f(v)} for n, v in zip(names, mdl.feature_importances_)]
        elif hasattr(mdl, "coef_"):
            vals = np.mean(np.abs(mdl.coef_), axis=0)
            coef = [{"feature": n, "value": _f(v)} for n, v in zip(names, vals)]
        artifacts["coefficients"] = sorted(coef, key=lambda d: -(d["value"] or 0))[:20]
    except Exception:
        pass
    # ROC فقط برای دوکلاسه با احتمال
    if len(labels) == 2 and hasattr(mdl, "predict_proba"):
        try:
            proba = mdl.predict_proba(Xte)[:, 1]
            auc = _f(M.roc_auc_score(yte, proba))
            fpr, tpr, _ = M.roc_curve(yte, proba)
            pts = _downsample_pairs([{"fpr": _f(a, 3), "tpr": _f(b, 3)} for a, b in zip(fpr, tpr)], 150)
            artifacts["roc"] = {"points": pts, "auc": auc, "positive_class": labels[1]}
            metrics["roc_auc_test"] = auc
        except Exception:
            pass
    return metrics, artifacts


def _pca2(X):
    from sklearn.decomposition import PCA
    n = min(2, X.shape[1])
    if n < 2:
        return None
    try:
        return PCA(n_components=2, random_state=42).fit(X)
    except Exception:
        return None


def _run_clustering(model_key, enc, params):
    from sklearn import metrics as M
    from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
    X, names = enc["X"], enc["feat_names"]
    X_raw = X.copy()          # برای پروفایل خوشه‌ها با مقیاس اصلی
    seed = int(params.get("random_state", 42))
    scaled = params.get("scaled", True)
    if scaled:
        from sklearn.preprocessing import StandardScaler
        X = StandardScaler().fit_transform(X)

    def _silhouette(lbl):
        u = set(lbl.tolist())
        if len(u) < 2 or len(u) >= len(lbl):
            return None
        try:
            return _f(M.silhouette_score(X, lbl, sample_size=min(1500, len(lbl)), random_state=seed))
        except Exception:
            return None

    artifacts, extra = {}, {}
    if model_key == "kmeans":
        k = params.get("k")
        elbow = []
        for kk in range(1, 9):
            km = KMeans(n_clusters=kk, n_init=10, random_state=seed).fit(X)
            elbow.append({"k": kk, "inertia": _f(km.inertia_)})
        if not k:
            best, best_s = None, -2
            for kk in range(2, 7):
                lbl = KMeans(n_clusters=kk, n_init=10, random_state=seed).fit_predict(X)
                s = _silhouette(lbl)
                if s is not None and s > best_s:
                    best, best_s = kk, s
            k = best or 3
        mdl = KMeans(n_clusters=int(k), n_init=10, random_state=seed).fit(X)
        labels = mdl.labels_
        extra = {"elbow": elbow, "k_chosen": int(k), "auto": not params.get("k")}
        artifacts["pca_centroids"] = None  # بعد از PCA پر می‌شود
        centroids = mdl.cluster_centers_
    elif model_key == "hierarchical":
        k = int(params.get("k", 3))
        if k >= len(X):
            raise HTTPException(status_code=400, detail="تعداد خوشه باید کمتر از تعداد ردیف‌ها باشد")
        labels = AgglomerativeClustering(n_clusters=k).fit_predict(X)
        centroids = np.vstack([X[labels == c].mean(axis=0) for c in range(k)])
        extra = {"k_chosen": int(k)}
    else:  # dbscan
        eps = params.get("eps")
        if not eps:
            from sklearn.neighbors import NearestNeighbors
            nn = NearestNeighbors(n_neighbors=min(6, len(X))).fit(X)
            dist, _ = nn.kneighbors(X)
            eps = float(np.mean(dist[:, -1]))
        min_samples = _ip(params, "min_samples", 5)
        labels = DBSCAN(eps=float(eps), min_samples=min_samples).fit_predict(X)
        centroids = np.vstack([X[labels == c].mean(axis=0) for c in sorted(set(labels.tolist())) if c >= 0]) \
            if len(set(labels.tolist()) - {-1}) else None
        extra = {"eps_used": _f(eps), "min_samples": min_samples}

    uniq = sorted(set(labels.tolist()))
    metrics = {
        "n_clusters": int(len([u for u in uniq if u >= 0])),
        "cluster_sizes": {str(int(u)): int((labels == u).sum()) for u in uniq},
        "silhouette": _silhouette(labels),
        **extra,
    }
    if model_key == "dbscan":
        metrics["noise_points"] = int((labels == -1).sum())
    if model_key == "kmeans":
        metrics["inertia"] = _f(getattr(mdl, "inertia_", None))

    # پروفایل هر خوشه: میانگین ویژگی‌های عددی در مقیاس اصلی (تفسیرپذیر)
    profile = []
    for u in uniq:
        if u < 0:
            continue
        profile.append({"cluster": int(u), "size": int((labels == u).sum()),
                        "means": {n: _f(v) for n, v in zip(names, (X_raw[labels == u].mean(axis=0)))}})
    artifacts["cluster_profile"] = profile

    # تصویر دوبعدی PCA برای نمودار
    pca = _pca2(X)
    if pca is not None:
        P = pca.transform(X)
        pts = [{"x": _f(p[0]), "y": _f(p[1]), "cluster": int(l)} for p, l in zip(P, labels)]
        artifacts["pca_scatter"] = _downsample_pairs(pts, SAMPLE_SCATTER)
        artifacts["pca_variance"] = [_f(v, 3) for v in pca.explained_variance_ratio_]
        if model_key == "kmeans" and centroids is not None:
            C = pca.transform(centroids)
            artifacts["pca_centroids"] = [{"x": _f(c[0]), "y": _f(c[1]), "cluster": int(i)}
                                          for i, c in enumerate(C)]
    return metrics, artifacts


# ============================================================
# اندپوینت‌های دیتاست
# ============================================================

@router.get("/meta", summary="فهرست وظایف، مدل‌ها و برچسب‌های فارسی برای رابط کاربری")
def meta():
    return {"tasks": [{"key": k, "title": v["title"],
                       "models": [{"key": mk, "title": mv} for mk, mv in v["models"].items()]}
                      for k, v in TASKS.items()],
            "limits": {"max_rows": MAX_ROWS, "max_cols": MAX_COLS, "max_upload_bytes": MAX_UPLOAD_BYTES}}


@router.post("/datasets", summary="بارگذاری دیتاست (CSV یا XLSX) با تشخیص خودکار نوع ستون‌ها")
def upload_dataset(file: UploadFile = File(...), title: str = Form(""),
                   description: str = Form(""), project_id: int | None = Form(None),
                   research_doc_id: int | None = Form(None),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    raw = file.file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="فایل خالی است")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"حجم فایل بیش از {MAX_UPLOAD_BYTES // (1024 * 1024)} مگابایت است")
    name = (file.filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        rows, meta = _parse_xlsx(raw)
    elif name.endswith((".csv", ".txt", ".tsv")):
        rows, meta = _parse_csv(raw)
    else:
        raise HTTPException(status_code=400, detail="فرمت فایل باید csv، txt، tsv یا xlsx باشد")
    if len(rows) > MAX_ROWS:
        raise HTTPException(status_code=400, detail=f"بیشتر از {MAX_ROWS} ردیف مجاز نیست؛ نمونهٔ کوچک‌تری بارگذاری کنید")
    if len(meta) > MAX_COLS:
        raise HTTPException(status_code=400, detail=f"بیشتر از {MAX_COLS} ستون مجاز نیست")
    if project_id or research_doc_id:
        from ..models import Project, ResearchDoc
        if project_id and not db.get(Project, project_id):
            raise HTTPException(status_code=404, detail="پروژهٔ پیوند یافت نشد")
        if research_doc_id and not db.get(ResearchDoc, research_doc_id):
            raise HTTPException(status_code=404, detail="سند پژوهشی پیوند یافت نشد")
    d = LabDataset(owner_id=user.id, title=(title or file.filename or "دیتاست بدون عنوان").strip()[:300],
                   description=description, filename=file.filename or "", size=len(raw),
                   n_rows=len(rows), n_cols=len(meta), columns_meta=meta, rows=rows,
                   project_id=project_id, research_doc_id=research_doc_id)
    db.add(d)
    log_event(db, "lab_dataset_created", user.id, {"dataset_id": d.id, "rows": len(rows), "cols": len(meta)})
    db.commit()
    return _ser_dataset(d)


@router.get("/datasets", summary="دیتاست‌های من")
def my_datasets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(LabDataset).filter(LabDataset.owner_id == user.id)
            .order_by(LabDataset.created_at.desc()).limit(200).all())
    return [_ser_dataset(d) for d in rows]


@router.get("/datasets/all", summary="همهٔ دیتاست‌ها (مدیر پژوهش)")
def all_datasets(user: User = Depends(require_roles("research_manager", "system_admin")),
                 db: Session = Depends(get_db)):
    rows = db.query(LabDataset).order_by(LabDataset.created_at.desc()).limit(300).all()
    return [_ser_dataset(d) for d in rows]


@router.get("/datasets/{ds_id}", summary="نمای دیتاست: فرادادهٔ ستون‌ها + پیش‌نمایش ردیف‌ها")
def dataset_detail(ds_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _get_dataset_checked(db, ds_id, user)
    out = _ser_dataset(d)
    out["preview"] = (d.rows or [])[:20]
    return out


@router.delete("/datasets/{ds_id}", summary="حذف دیتاست به‌همراه آزمایش‌هایش (صاحب دیتاست)")
def delete_dataset(ds_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _get_dataset_checked(db, ds_id, user)
    if d.owner_id != user.id and not (set(user.roles or []) & {"system_admin"}):
        raise HTTPException(status_code=403, detail="فقط صاحب دیتاست می‌تواند حذف کند")
    n = db.query(LabExperiment).filter(LabExperiment.dataset_id == ds_id).count()
    db.query(LabExperiment).filter(LabExperiment.dataset_id == ds_id).delete()
    db.delete(d)
    log_event(db, "lab_dataset_deleted", user.id, {"dataset_id": ds_id, "experiments_removed": n})
    db.commit()
    return {"ok": True, "experiments_removed": n}


@router.get("/datasets/{ds_id}/profile", summary="پروفایل توصیفی کامل: آماره‌ها، توزیع، مقوله‌ها، دادهٔ گمشده")
def dataset_profile(ds_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _get_dataset_checked(db, ds_id, user)
    rows = d.rows or []
    n = len(rows)
    cols = []
    for c in (d.columns_meta or []):
        name, dtype = c["name"], c["dtype"]
        vals = [r.get(name) for r in rows]
        missing = sum(1 for v in vals if v is None)
        base = {"name": name, "dtype": dtype, "n_missing": missing,
                "missing_ratio": _f(missing / n, 3) if n else 0}
        if dtype == "numeric":
            arr = np.array([v for v in vals if isinstance(v, (int, float))], dtype=float)
            if arr.size:
                q1, med, q3 = np.percentile(arr, [25, 50, 75])
                iqr = q3 - q1
                lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                base.update({"count": int(arr.size), "mean": _f(arr.mean()), "std": _f(arr.std()),
                             "min": _f(arr.min()), "q1": _f(q1), "median": _f(med), "q3": _f(q3),
                             "max": _f(arr.max()), "outliers": int(((arr < lo) | (arr > hi)).sum()),
                             "hist": _histogram(vals, 24)})
        else:
            counts = Counter(str(v) for v in vals if v is not None)
            base.update({"n_unique": len(counts),
                         "top": [{"value": k, "count": v} for k, v in counts.most_common(15)]})
        cols.append(base)
    dup = n - len({tuple(sorted((k, str(v)) for k, v in r.items())) for r in rows}) if rows else 0
    missing_cells = sum(c["n_missing"] for c in cols)
    return {"dataset_id": d.id, "title": d.title, "n_rows": n, "n_cols": len(cols),
            "duplicate_rows": int(dup),
            "missing_cells": int(missing_cells),
            "missing_ratio": _f(missing_cells / max(1, n * len(cols)), 3),
            "columns": cols}


@router.get("/datasets/{ds_id}/correlations", summary="ماتریس همبستگی پیرسون/اسپیرمن بین ستون‌های عددی + جفت‌های قوی")
def correlations(ds_id: int, method: str = "pearson",
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if method not in ("pearson", "spearman"):
        raise HTTPException(status_code=400, detail="روش باید pearson یا spearman باشد")
    d = _get_dataset_checked(db, ds_id, user)
    num = [c["name"] for c in (d.columns_meta or []) if c["dtype"] == "numeric"]
    if len(num) < 2:
        raise HTTPException(status_code=400, detail="برای همبستگی حداقل دو ستون عددی لازم است")
    arr = np.full((len(d.rows), len(num)), np.nan)
    for i, r in enumerate(d.rows or []):
        for j, c in enumerate(num):
            v = r.get(c)
            if isinstance(v, (int, float)):
                arr[i, j] = float(v)
    if method == "pearson":
        from scipy.stats import pearsonr
        fn = pearsonr
    else:
        from scipy.stats import spearmanr
        fn = spearmanr
    k = len(num)
    mat = [[None] * k for _ in range(k)]
    strong = []
    for i in range(k):
        for j in range(k):
            if i == j:
                mat[i][j] = 1.0
                continue
            if j < i:
                mat[i][j] = mat[j][i]
                continue
            a, b = arr[:, i], arr[:, j]
            m = np.isfinite(a) & np.isfinite(b)
            if m.sum() < 3 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
                continue
            r, p = fn(a[m], b[m])
            if np.isnan(r):
                continue
            mat[i][j] = _f(r)
            if abs(r) >= 0.7:
                strong.append({"a": num[i], "b": num[j], "r": _f(r),
                               "p_value": _f(p, 5),
                               "direction": "مستقیم" if r > 0 else "معکوس"})
    return {"method": method, "columns": num, "matrix": mat,
            "strong_pairs": sorted(strong, key=lambda s: -abs(s["r"])),
            "note": "همبستگی رابطهٔ خطی را نشان می‌دهد، نه رابطهٔ علّی؛ مقدار p برای معناداری آماری است."}


@router.get("/datasets/{ds_id}/scatter", summary="دادهٔ نمودار پراکندگی دو متغیر (با رنگ‌بندی اختیاری بر حسب یک ستون مقوله‌ای)")
def scatter(ds_id: int, x: str, y: str, hue: str | None = None,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _get_dataset_checked(db, ds_id, user)
    meta = {c["name"]: c for c in (d.columns_meta or [])}
    for s in ([x, y] + ([hue] if hue else [])):
        if s and s not in meta:
            raise HTTPException(status_code=400, detail=f"ستون «{s}» در دیتاست نیست")
    pts, groups = [], Counter()
    for r in (d.rows or []):
        xv, yv = r.get(x), r.get(y)
        if not isinstance(xv, (int, float)) or not isinstance(yv, (int, float)):
            continue
        g = str(r.get(hue)) if (hue and r.get(hue) is not None) else ""
        groups[g] += 1
        pts.append({"x": _f(xv), "y": _f(yv), "g": g})
    # خط رگرسیون ساده برای جهت رابطه
    slope = intercept = r = None
    xs = np.array([p["x"] for p in pts])
    ys = np.array([p["y"] for p in pts])
    if len(pts) >= 3 and np.std(xs) > 0 and np.std(ys) > 0:
        slope, intercept = np.polyfit(xs, ys, 1)
        r = _f(np.corrcoef(xs, ys)[0, 1])
    return {"x": x, "y": y, "hue": hue,
            "points": _downsample_pairs(pts, SAMPLE_SCATTER),
            "groups": [{"value": k, "count": v} for k, v in groups.most_common(20)],
            "trend": {"slope": _f(slope), "intercept": _f(intercept), "r": r},
            "n_valid": len(pts)}


@router.get("/datasets/{ds_id}/crosstab", summary="جدول توافقی دو ستون مقوله‌ای + آزمون کای‌دوی استقلال")
def crosstab(ds_id: int, a: str, b: str,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _get_dataset_checked(db, ds_id, user)
    meta = {c["name"]: c for c in (d.columns_meta or [])}
    for s in (a, b):
        if s not in meta:
            raise HTTPException(status_code=400, detail=f"ستون «{s}» در دیتاست نیست")
        if meta[s]["dtype"] == "numeric":
            raise HTTPException(status_code=400, detail=f"ستون «{s}» عددی است؛ برای جدول توافقی ستون مقوله‌ای انتخاب کنید")
    ta = Counter(str(r.get(a)) for r in (d.rows or []) if r.get(a) is not None)
    tb = Counter(str(r.get(b)) for r in (d.rows or []) if r.get(b) is not None)
    ra, cb = [k for k, _ in ta.most_common(10)], [k for k, _ in tb.most_common(10)]
    table = [[0] * len(cb) for _ in ra]
    for r in (d.rows or []):
        va, vb = r.get(a), r.get(b)
        if va is None or vb is None:
            continue
        sa, sb = str(va), str(vb)
        if sa in ra and sb in cb:
            table[ra.index(sa)][cb.index(sb)] += 1
    chi2, p, dof, note = None, None, None, ""
    try:
        from scipy.stats import chi2_contingency
        chi2, p, dof, _ = chi2_contingency(table)
        chi2, p, dof = _f(chi2), _f(p, 5), int(dof)
        note = ("ارتباط معنادار بین دو متغیر دیده می‌شود (p < 0.05)." if p is not None and p < 0.05
                else "شواهد ارتباط معنادار کافی نیست (p ≥ 0.05).")
    except Exception as e:
        note = f"آزمون کای‌دو اجرا نشد: {e}"
    return {"a": a, "b": b, "rows_labels": ra, "cols_labels": cb, "table": table,
            "chi2": chi2, "p_value": p, "dof": dof, "note": note}


@router.get("/datasets/{ds_id}/anova", summary="تحلیل واریانس یک‌راهه: مقایسهٔ میانگین یک متغیر عددی در گروه‌های مقوله‌ای")
def anova(ds_id: int, target: str, group: str,
          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _get_dataset_checked(db, ds_id, user)
    meta = {c["name"]: c for c in (d.columns_meta or [])}
    if target not in meta or group not in meta:
        raise HTTPException(status_code=400, detail="ستون هدف یا گروه در دیتاست نیست")
    if meta[target]["dtype"] != "numeric":
        raise HTTPException(status_code=400, detail="متغیر پاسخ (target) باید عددی باشد")
    if meta[group]["dtype"] == "numeric":
        raise HTTPException(status_code=400, detail="متغیر گروه‌بندی باید مقوله‌ای باشد")
    groups = {}
    for r in (d.rows or []):
        v, g = r.get(target), r.get(group)
        if isinstance(v, (int, float)) and g is not None:
            groups.setdefault(str(g), []).append(float(v))
    groups = {k: v for k, v in groups.items() if len(v) >= 3}
    if len(groups) < 2:
        raise HTTPException(status_code=400, detail="برای ANOVA حداقل دو گروه با سه مشاهده لازم است")
    from scipy.stats import f_oneway
    keys = list(groups.keys())
    F, p = f_oneway(*[groups[k] for k in keys])
    eta2 = None
    try:
        all_v = [x for k in keys for x in groups[k]]
        ss_between = sum(len(groups[k]) * (np.mean(groups[k]) - np.mean(all_v)) ** 2 for k in keys)
        ss_total = sum((x - np.mean(all_v)) ** 2 for x in all_v)
        eta2 = _f(ss_between / ss_total, 3) if ss_total else None
    except Exception:
        pass
    return {"target": target, "group": group,
            "groups": [{"value": k, "n": len(groups[k]), "mean": _f(np.mean(groups[k])),
                        "std": _f(np.std(groups[k]))} for k in keys],
            "F": _f(F), "p_value": _f(p, 5), "eta_squared": eta2,
            "note": ("میانگین گروه‌ها تفاوت معنادار دارد (p < 0.05)." if p < 0.05
                     else "تفاوت معنادار میان گروه‌ها اثبات نشد (p ≥ 0.05).")}


# ============================================================
# اندپوینت‌های آزمایش (شبیه‌سازی مدل)
# ============================================================

class ExperimentIn(BaseModel):
    dataset_id: int
    task: str                      # regression | classification | clustering
    model: str
    target: str = ""
    features: list[str] = []
    title: str = ""
    params: dict = {}


class PredictIn(BaseModel):
    row: dict


class AttachDocIn(BaseModel):
    doc_id: int
    section_id: int | None = None


@router.post("/experiments", summary="اجرای آزمایش شبیه‌سازی: آموزش مدل، محاسبهٔ سنجه‌ها و دادهٔ نمودارها")
def run_experiment(body: ExperimentIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if body.task not in TASKS:
        raise HTTPException(status_code=400, detail="وظیفه باید regression، classification یا clustering باشد")
    if body.model not in TASKS[body.task]["models"]:
        raise HTTPException(status_code=400, detail="مدل انتخابی با وظیفه سازگار نیست")
    if body.task == "clustering":
        if len(body.features) < 2:
            raise HTTPException(status_code=400, detail="برای خوشه‌بندی حداقل دو ویژگی عددی انتخاب کنید")
    else:
        if not body.target:
            raise HTTPException(status_code=400, detail="ستون هدف را انتخاب کنید")
        if not body.features:
            raise HTTPException(status_code=400, detail="حداقل یک ویژگی (متغیر مستقل) انتخاب کنید")
        if body.target in body.features:
            raise HTTPException(status_code=400, detail="ستون هدف نمی‌تواند هم‌زمان ویژگی باشد")
    d = _get_dataset_checked(db, body.dataset_id, user)

    exp = LabExperiment(dataset_id=d.id, owner_id=user.id,
                        title=(body.title or f"{TASKS[body.task]['title']} — {TASKS[body.task]['models'][body.model]}"),
                        task=body.task, model=body.model,
                        model_fa=TASKS[body.task]["models"][body.model], target=body.target,
                        features=body.features[:MAX_COLS],
                        params={"test_size": float(body.params.get("test_size", 0.25)),
                                "random_state": int(body.params.get("random_state", 42)),
                                "scaled": bool(body.params.get("scaled", False)),
                                "k": body.params.get("k"), "eps": body.params.get("eps"),
                                "min_samples": body.params.get("min_samples"),
                                "alpha": body.params.get("alpha"),
                                "max_depth": body.params.get("max_depth"),
                                "n_estimators": body.params.get("n_estimators")})
    db.add(exp)
    db.flush()
    try:
        enc = _encode_matrix(d.rows or [], exp.features, d.columns_meta, target=exp.target, task=exp.task)
        if exp.task == "regression":
            metrics, artifacts = _run_regression(exp.model, enc, exp.params)
        elif exp.task == "classification":
            metrics, artifacts = _run_classification(exp.model, enc, exp.params)
        else:
            metrics, artifacts = _run_clustering(exp.model, enc, exp.params)
        metrics["n_rows_total"] = int(len(d.rows or []))
        exp.metrics, exp.artifacts, exp.status = metrics, artifacts, "completed"
        log_event(db, "lab_experiment_run", user.id,
                  {"experiment_id": exp.id, "task": exp.task, "model": exp.model, "dataset_id": d.id})
        db.commit()
        return _ser_experiment(exp)
    except HTTPException:
        exp.status, exp.error = "failed", "ورودی نامعتبر"
        db.commit()
        raise
    except Exception as e:
        exp.status, exp.error = "failed", f"{type(e).__name__}: {e}"[:400]
        db.commit()
        raise HTTPException(status_code=400, detail=f"اجرای مدل ناموفق بود: {e}")


@router.get("/experiments", summary="آزمایش‌های من (قابل فیلتر بر حسب دیتاست)")
def my_experiments(dataset_id: int | None = None, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    q = db.query(LabExperiment).filter(LabExperiment.owner_id == user.id)
    if dataset_id:
        q = q.filter(LabExperiment.dataset_id == dataset_id)
    rows = q.order_by(LabExperiment.created_at.desc()).limit(200).all()
    return [_ser_experiment(e, with_artifacts=False) for e in rows]


@router.get("/experiments/{exp_id}", summary="نمای کامل آزمایش با سنجه‌ها و نمودارها")
def experiment_detail(exp_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = db.get(LabExperiment, exp_id)
    if not e:
        raise HTTPException(status_code=404, detail="آزمایش یافت نشد")
    _get_dataset_checked(db, e.dataset_id, user)  # دسترسی از طریق دیتاست
    out = _ser_experiment(e)
    out["dataset_title"] = db.get(LabDataset, e.dataset_id).title
    return out


@router.delete("/experiments/{exp_id}", summary="حذف آزمایش")
def delete_experiment(exp_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = db.get(LabExperiment, exp_id)
    if not e:
        raise HTTPException(status_code=404, detail="آزمایش یافت نشد")
    if e.owner_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط سازندهٔ آزمایش یا مدیر می‌تواند حذف کند")
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.post("/experiments/{exp_id}/predict", summary="پیش‌بینی برای یک ردیف جدید با مدل همان آزمایش (بازآموزی قطعی از پارامترهای ثبت‌شده)")
def predict_one(exp_id: int, body: PredictIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    e = db.get(LabExperiment, exp_id)
    if not e or e.status != "completed":
        raise HTTPException(status_code=404, detail="آزمایش کامل‌شده‌ای با این شناسه نیست")
    _get_dataset_checked(db, e.dataset_id, user)
    d = db.get(LabDataset, e.dataset_id)
    try:
        enc = _encode_matrix(d.rows or [], e.features, d.columns_meta, target=e.target, task=e.task)
        x = _encode_one(body.row or {}, e.features, d.columns_meta, enc)
        if e.task == "clustering":
            from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
            from sklearn.preprocessing import StandardScaler
            X = enc["X"]
            if e.params.get("scaled", True):
                X = StandardScaler().fit_transform(X)
                x = StandardScaler().fit(np.vstack([enc["X"], x])).transform(x)[-1].reshape(1, -1)
            if e.model == "kmeans":
                mdl = KMeans(n_clusters=int(e.metrics.get("k_chosen", 3)), n_init=10,
                             random_state=int(e.params.get("random_state", 42))).fit(X)
                return {"prediction": int(mdl.predict(x)[0])}
            if e.model == "hierarchical":
                lbl = AgglomerativeClustering(n_clusters=int(e.metrics.get("k_chosen", 3))).fit_predict(
                    np.vstack([X, x]))
                return {"prediction": int(lbl[-1]),
                        "note": "خوشهٔ سلسله‌مراتبی با الحاق ردیف جدید بازتخصیص شد"}
            # DBSCAN: همان پارامترها بازاجرایی می‌شود و نزدیک‌ترین نقطهٔ غیرنویز گزارش می‌شود
            from sklearn.neighbors import NearestNeighbors
            lbl = DBSCAN(eps=float(e.params.get("eps") or e.metrics.get("eps_used") or 0.5),
                         min_samples=int(e.params.get("min_samples") or e.metrics.get("min_samples") or 5)
                         ).fit_predict(X)
            core_idx = np.where(lbl >= 0)[0]
            if core_idx.size == 0:
                return {"prediction": None, "note": "در بازاجرای DBSCAN هیچ خوشه‌ای شکل نگرفت"}
            nn = NearestNeighbors(n_neighbors=1).fit(X[core_idx])
            dist, ind = nn.kneighbors(x)
            return {"prediction": int(lbl[core_idx[ind[0][0]]]), "distance": _f(dist[0][0]),
                    "note": "برچسب نزدیک‌ترین نقطهٔ هستهٔ DBSCAN به ردیف شما"}
        if e.task == "regression":
            mdl = _regressor(e.model, e.params)
            mdl.fit(enc["X"], enc["y"])
            return {"prediction": _f(mdl.predict(x)[0])}
        mdl = _classifier(e.model, e.params)
        mdl.fit(enc["X"], enc["y"])
        labels = enc["target_meta"]["labels"]
        p = mdl.predict(x)[0]
        out = {"prediction": labels[int(p)]}
        if hasattr(mdl, "predict_proba"):
            proba = mdl.predict_proba(x)[0]
            out["probabilities"] = {labels[i]: _f(v, 4) for i, v in enumerate(proba)}
        return out
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=400, detail=f"پیش‌بینی ناموفق بود: {ex}")


@router.post("/experiments/{exp_id}/attach-doc", summary="درج خلاصهٔ نتایج آزمایش در بخش «یافته‌ها»ی سند پژوهش تیمی")
def attach_to_doc(exp_id: int, body: AttachDocIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    from ..models import DocSection
    from .research import require_doc_access
    e = db.get(LabExperiment, exp_id)
    if not e or e.status != "completed":
        raise HTTPException(status_code=404, detail="آزمایش کامل‌شده‌ای با این شناسه نیست")
    # سیاست: سازندهٔ آزمایش (یا مدیر) نتیجه را در سندی که دسترسی نگارش دارد درج می‌کند
    if e.owner_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط سازندهٔ آزمایش یا مدیر می‌تواند نتیجه را در سند درج کند")
    m = require_doc_access(db, body.doc_id, user, min_role="writer")
    if m is None and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط اعضای نویسندهٔ سند می‌توانند نتیجه درج کنند")
    sections = db.query(DocSection).filter(DocSection.doc_id == body.doc_id).order_by(DocSection.ord).all()
    if not sections:
        raise HTTPException(status_code=400, detail="سند بخشی ندارد")
    sec = None
    if body.section_id:
        sec = db.get(DocSection, body.section_id)
        if not sec or sec.doc_id != body.doc_id:
            raise HTTPException(status_code=404, detail="بخش مقصد یافت نشد")
    else:
        keys = ("یافته", "نتایج", "Results", "Evaluation", "Experiments")
        sec = next((s for s in sections if any(k in (s.heading or "") for k in keys)), sections[-1])
    d = db.get(LabDataset, e.dataset_id)
    mt = e.metrics or {}
    lines = [f"نتایج شبیه‌سازی (آزمایشگاه پژوهشیار۳۶۰، آزمایش شمارهٔ {e.id}):",
             f"مدل «{e.model_fa}» روی دیتاست «{d.title}» با {mt.get('n_rows_total')} ردیف آموزش دیده است؛ "
             f"{mt.get('n_train')} ردیف آموزش و {mt.get('n_test')} ردیف آزمون (تقسیم آزمون "
             f"{e.params.get('test_size')}, بذر تصادفی {e.params.get('random_state')})."]
    if e.task == "regression":
        lines.append(f"مجموعهٔ آزمون: R² = {mt.get('r2_test')}، MAE = {mt.get('mae_test')}، "
                     f"RMSE = {mt.get('rmse_test')}.")
    elif e.task == "classification":
        lines.append(f"مجموعهٔ آزمون: دقت = {mt.get('accuracy_test')}، F1 کلان = {mt.get('f1_macro_test')}"
                     + (f"، AUC = {mt.get('roc_auc_test')}" if mt.get("roc_auc_test") else "") + ".")
    else:
        lines.append(f"الگوی داده: {mt.get('n_clusters')} خوشه شناسایی شد"
                     + (f" با ضریب سایه‌لو {mt.get('silhouette')}" if mt.get("silhouette") else "") + ".")
    coefs = (e.artifacts or {}).get("coefficients") or []
    if coefs:
        top = "؛ ".join(f"{c['feature']} ({c['value']})" for c in coefs[:5])
        lines.append(f"مهم‌ترین متغیرها به‌ترتیب اهمیت/ضریب: {top}.")
    lines.append("این متن به‌صورت خودکار از نتایج آزمایش سامانه تولید شده و باید بازنویسی و تفسیر انسانی شود.")
    sep = "\n\n" if (sec.body or "").strip() else ""
    sec.body = (sec.body or "") + sep + "\n".join(lines)
    sec.version_no += 1
    sec.updated_by = user.id
    log_event(db, "lab_result_attached", user.id,
              {"experiment_id": e.id, "doc_id": body.doc_id, "section_id": sec.id})
    db.commit()
    return {"ok": True, "section_id": sec.id, "section_heading": sec.heading}
