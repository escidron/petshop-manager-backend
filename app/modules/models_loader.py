import pkgutil
import importlib
import app.modules


def load_all_models():
    for _, module_name, _ in pkgutil.iter_modules(app.modules.__path__):
        try:
            importlib.import_module(f"app.modules.{module_name}.models")
        except ModuleNotFoundError:
            pass
