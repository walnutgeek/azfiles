from setuptools import find_packages, setup

cmdclass_dict = {}  # type:ignore

# MANIFEST.in ensures that readme and version included into sdist

install_requires = [
    "requests", "python-dateutil"
]

dev_requires = [
    "hs-build-tools",
    "coverage",
    "mypy",
    "wheel",
    "twine",
    "black",
    "isort",
    "pytest",
    "pytest-mypy",
    "pytest-cov",
    "types-python-dateutil",
    "types-requests",
]


def read_file(f):
    with open(f, "r") as fh:
        return fh.read()


long_description = read_file("README.md")

try:
    from hs_build_tools.release import get_version_and_add_release_cmd

    version = get_version_and_add_release_cmd("version.txt",
                                              cmdclass_dict)
except ModuleNotFoundError:
    version = read_file("version.txt").strip()

setup(
    name="azfiles",
    version=str(version),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: System :: Archiving :: Backup",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    description="Work with file shares in azure via REST API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/walnutgeek/azfiles",
    author="Walnut Geek",
    author_email="wg@walnutgeek.com",
    license="Apache 2.0",
    packages=find_packages(exclude=("*.tests",)),
    cmdclass=cmdclass_dict,
    entry_points={"console_scripts": ["azfiles=azfiles:main"]},
    install_requires=install_requires,
    extras_require={"dev": dev_requires},
    zip_safe=False,
)
