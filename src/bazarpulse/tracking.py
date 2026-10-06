"""MLflow experiment tracking.

Logs to MLFLOW_TRACKING_URI when it is set (e.g. a free DagsHub MLflow server, with
MLFLOW_TRACKING_USERNAME / MLFLOW_TRACKING_PASSWORD), otherwise to ./mlruns.
Tracking is best-effort: an unreachable server never stops training or the pipeline.
"""
import contextlib
import os

EXPERIMENT = "bazar-pulse"


def _start(name, params, log):
    # MLflow 3 refuses the plain ./mlruns folder unless asked; it is fine for a local log.
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    try:
        import mlflow
        uri = os.environ.get("MLFLOW_TRACKING_URI") or "file:" + os.path.abspath("mlruns").replace("\\", "/")
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(EXPERIMENT)
        mlflow.start_run(run_name=name)
        if params:
            mlflow.log_params({k: v for k, v in params.items() if v is not None})
        return mlflow
    except Exception as e:
        log(f"  [mlflow] tracking disabled for this run: {type(e).__name__}: {e}")
        return None


@contextlib.contextmanager
def run(name, params=None, log=print):
    ml = _start(name, params, log)
    try:
        yield ml
    finally:
        if ml is not None:
            with contextlib.suppress(Exception):
                ml.end_run()


def log_metrics(ml, metrics, prefix=""):
    if ml is None:
        return
    with contextlib.suppress(Exception):
        ml.log_metrics({f"{prefix}{k}": float(v) for k, v in metrics.items()
                        if isinstance(v, (int, float))})


def log_artifact(ml, path):
    if ml is None:
        return
    with contextlib.suppress(Exception):
        ml.log_artifact(path)
