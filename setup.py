# pylint: disable=missing-module-docstring
#import setuptools
#
#if __name__ == "__main__":
#    setuptools.setup(use_scm_version=True)
# pylint: disable=missing-module-docstring
import setuptools
from setuptools import setup, find_packages

#if __name__ == "__main__":
#    setuptools.setup(use_scm_version=True)


setup(
        name="saltext",
        version="1.0",
        author="Cohesity",
        packages=find_packages()
        )

