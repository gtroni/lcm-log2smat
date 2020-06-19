"""Setup script for pylcm python package."""

import setuptools

setuptools.setup(
    name="pylcm",
    version="0.1",
    description="Python package for parsing LCM logs.",
    url="https://github.com/DexaiRobotics/lcm-log2smat/",
    packages=setuptools.find_packages(),
    python_requires=">=3.6",
    install_requires=["scipy>=1.4.1",],
)
