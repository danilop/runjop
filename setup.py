from setuptools import setup


setup(
        name="runjop",
        version="1.0",
        author="Danilo Poccia",
        install_requires="boto",
        entry_points = { 'console_scripts': ['runjop = runjop:main'] },
        );
