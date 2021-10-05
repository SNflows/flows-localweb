import glob
from setuptools import setup

files = glob.glob("src/web/**", recursive=True)
package_data = {"flows_localweb": list(map(lambda d: d.split('/', 1)[1], files))}

setup(
    name = "flows-localweb",
    version = "0.1a0",
    packages = ["flows_localweb"],
    package_dir = {"flows_localweb": "./src"},
    install_requires = ["flask"],
    entry_points = {
        "console_scripts": [
            "flows-localweb = flows_localweb.localweb:main",
        ]
    },
    package_data = package_data,
    include_package_data = True
)
