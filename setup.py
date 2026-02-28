from setuptools import find_packages, setup


setup(
    name="resilienceos",
    version="0.1.0",
    description="AI resilience agent for neighborhood environmental crisis preparedness",
    package_dir={"": "src"},
    packages=find_packages("src"),
    include_package_data=True,
    install_requires=["typer>=0.12", "pydantic>=2.8", "jinja2>=3.1"],
    entry_points={"console_scripts": ["resilienceos = resilienceos.cli:app"]},
)
