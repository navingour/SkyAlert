from pathlib import Path
import yaml


BASE_DIR = Path(__file__).resolve().parent.parent.parent

CONFIG_FILE = BASE_DIR / "config" / "config.yaml"


from app.config import load_config


class ConfigManager:

    def load(self):

        return load_config()


    def save(self, config):

        with open(CONFIG_FILE, "w") as f:

            yaml.dump(
                config,
                f,
                sort_keys=False
            )

        try:
            from app.collector.engine import collector_engine
            collector_engine.reload_config()
        except Exception:
            pass


config_manager = ConfigManager()
