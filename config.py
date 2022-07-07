import json
import logging
from datetime import time

logger = logging.getLogger('cuebot')
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('cuebot.log')
console_handler = logging.StreamHandler()
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
file_handler.level = logging.INFO
console_handler.level = logging.INFO
logger.addHandler(file_handler)
logger.addHandler(console_handler)


class Config:
    __instance = None

    @staticmethod
    def get_instance():
        if Config.__instance is None:
            Config()
        logger.info("Configuration instance ready.")
        return Config.__instance

    def __init__(self):
        if Config.__instance is not None:
            logger.warning("Using existing configuration instance.")
        else:
            logger.info("Generating config instance.")
            self.bot_key, self.refresh, self.superuser_id, self.superuser_ref, self.sre_us_start, self.sre_us_end, \
                self.sre_eu_start, self.sre_eu_end = None, None, None, None, None, None, None, None
            Config.__instance = self
            self.set_fallbackdata()
            self.load_config()
            self.parse_config()
            self.write_config()

    def load_config(self):
        try:
            with open("config.json", "r") as config_file:
                self.data = json.load(config_file)
                config_file.close()
                logger.info("Successfully loaded config file.")
        except:
            logger.warning("Failed to load config file.")
            self.data = {}

    def dump_config(self):
        config_dict = {"token": self.bot_key, "refresh": self.refresh,
                       "superuser_id": self.superuser_id, "superuser_ref": self.superuser_ref,
                       "sre_us_start": self.sre_us_start, "sre_us_end": self.sre_us_end,
                       "sre_eu_start": self.sre_eu_start, "sre_eu_end": self.sre_eu_end}
        return json.dumps(config_dict, indent=2)

    def write_config(self):
        try:
            with open("config.json", 'w') as config_writer:
                config_writer.write(self.dump_config())
                config_writer.close()
                logger.info("Successfully wrote config to file.")
        except Exception:
            logger.warning("Failed to write config to file.")

    def set_fallbackdata(self):
        self.fallbackdata = {"token": None,
                             "refresh": 15,
                             "superuser_id": None,
                             "superuser_ref": None,
                             "sre_us_start": {"utc_hour": 1, "utc_minute": 0},
                             "sre_us_end": {"utc_hour": 7, "utc_minute": 0},
                             "sre_eu_start": {"utc_hour": 16, "utc_minute": 0},
                             "sre_eu_end": {"utc_hour": 22, "utc_minute": 0}}

    def parse_config(self):
        if self.data.get("token") is not None:
            self.bot_key = self.data.get("token")
        else:
            self.bot_key = self.fallbackdata.get("token")

        if self.data.get("refresh") is not None:
            self.refresh = self.data.get("refresh")
        else:
            self.refresh = self.fallbackdata.get("refresh")

        if self.data.get("superuser_id") is not None:
            self.superuser_id = self.data.get("superuser_id")
        else:
            self.superuser_id = self.fallbackdata.get("superuser_id")

        if self.data.get("superuser_ref") is not None:
            self.superuser_ref = self.data.get("superuser_ref")
        else:
            self.superuser_ref = self.fallbackdata.get("superuser_ref")

        if self.data.get("sre_us_start") is not None:
            self.sre_us_start = self.data.get("sre_us_start")
        else:
            self.sre_us_start = self.fallbackdata.get("sre_us_start")

        if self.data.get("sre_us_end") is not None:
            self.sre_us_end = self.data.get("sre_us_end")
        else:
            self.sre_us_end = self.fallbackdata.get("sre_us_end")

        if self.data.get("sre_eu_start") is not None:
            self.sre_eu_start = self.data.get("sre_eu_start")
        else:
            self.sre_eu_start = self.fallbackdata.get("sre_eu_start")

        if self.data.get("sre_eu_end") is not None:
            self.sre_eu_end = self.data.get("sre_eu_end")
        else:
            self.sre_eu_end = self.fallbackdata.get("sre_eu_end")

    def get_token(self):
        return self.bot_key

    def get_refresh_timer(self):
        return self.refresh

    def get_superuser_id(self):
        return self.superuser_id

    def get_superuser_ref(self):
        return self.superuser_ref

    def get_sre_us_start(self):
        return time(hour=self.sre_us_start.get("utc_hour"), minute=self.sre_us_start.get("utc_minute"))

    def get_sre_us_end(self):
        return time(hour=self.sre_us_end.get("utc_hour"), minute=self.sre_us_end.get("utc_minute"))

    def get_sre_eu_start(self):
        return time(hour=self.sre_eu_start.get("utc_hour"), minute=self.sre_eu_start.get("utc_minute"))

    def get_sre_eu_end(self):
        return time(hour=self.sre_eu_end.get("utc_hour"), minute=self.sre_eu_end.get("utc_minute"))
