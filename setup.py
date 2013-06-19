from setuptools import setup
import sys

install_requires = ["boto"]

# Versions of Python pre-2.7 require argparse separately. 2.7+ and 3+ all
# include this as the replacement for optparse.
if sys.version_info[:2] < (2, 7):
    install_requires.append("argparse")

setup(
  name="runjop",
  version="1.0",
  author="Danilo Poccia",
  install_requires=install_requires,
  entry_points = { 'console_scripts': ['runjop = runjop:main'] },
);
