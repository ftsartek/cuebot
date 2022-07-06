import json
import logging

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
            self.bot_key, self.refresh, self.superuser_id, self.superuser_ref = None, None, None, None
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
                       "superuser_id": self.superuser_id, "superuser_ref": self.superuser_ref}
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
                             "superuser_ref": None}

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
            self.bot_key = self.data.get("superuser_id")
        else:
            self.bot_key = self.fallbackdata.get("superuser_id")

        if self.data.get("superuser_ref") is not None:
            self.bot_key = self.data.get("superuser_ref")
        else:
            self.bot_key = self.fallbackdata.get("superuser_ref")

    def get_token(self):
        return self.bot_key

    def get_refresh_timer(self):
        return self.refresh

    def get_superuser_id(self):
        return self.superuser_id

    def get_superuser_ref(self):
        return self.superuser_ref
