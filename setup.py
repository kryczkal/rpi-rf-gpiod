from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, "README.rst"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="rpi-rf-gpiod",
    version="1.0.0",
    author="Łukasz Kryczka",
    author_email="lukasz.kryczka000@gmail.com",
    description="Sending and receiving 433/315MHz signals with low-cost GPIO RF modules on a Raspberry Pi using the gpiod v2 API.",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/kryczkal/rpi-rf-gpiod",
    license="MIT",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Hardware :: Hardware Drivers",
    ],
    keywords=[
        "rpi",
        "raspberry",
        "raspberry pi",
        "rf",
        "gpio",
        "radio",
        "433",
        "433mhz",
        "315",
        "315mhz",
        "gpiod",
        "libgpiod",
        "libgpiod-python",
    ],
    install_requires=["gpiod>=2.0"],
    scripts=["scripts/rpi-rf_send", "scripts/rpi-rf_receive"],
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
)
