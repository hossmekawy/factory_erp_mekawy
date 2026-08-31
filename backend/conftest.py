"""Point the test run at the development database.

Django builds a throwaway `test_<name>` database either way, so production is
never touched — but naming it after the dev database keeps that obvious.
Settings reads DB_NAME from the environment first; python-dotenv does not
override a variable that is already set.
"""
import os

os.environ.setdefault("DB_NAME", "factory_erp_dev")
