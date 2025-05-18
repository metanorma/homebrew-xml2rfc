import codecs
import json
import logging
import re
import subprocess
import sys
import warnings
from contextlib import closing
from hashlib import sha256
from urllib.request import urlopen

import pkg_resources
from poet import merge_graphs, make_graph, PackageVersionNotFoundWarning


# Extracted from poet
def research_package(name, version=None, package_type='sdist'):
    with closing(urlopen("https://pypi.io/pypi/{}/json".format(name))) as f:
        reader = codecs.getreader("utf-8")
        pkg_data = json.load(reader(f))
    d = {}
    d['name'] = pkg_data['info']['name']
    d['homepage'] = pkg_data['info'].get('home_page', '')
    artefact = None
    if version:
        for pypi_version in pkg_data['releases']:
            if pkg_resources.safe_version(pypi_version) == version:
                for version_artefact in pkg_data['releases'][pypi_version]:
                    if version_artefact['packagetype'] == package_type:
                        artefact = version_artefact
                        break
        if artefact is None:
            warnings.warn("Could not find an exact version match for "
                          "{} version {}; using newest instead".
                          format(name, version), PackageVersionNotFoundWarning)

    if artefact is None:  # no version given or exact match not found
        for url in pkg_data['urls']:
            if url['packagetype'] == package_type:
                artefact = url
                break

    if artefact:
        d['url'] = artefact['url']
        if 'digests' in artefact and 'sha256' in artefact['digests']:
            logging.debug("Using provided checksum for %s", name)
            d['checksum'] = artefact['digests']['sha256']
        else:
            logging.debug("Fetching sdist to compute checksum for %s", name)
            with closing(urlopen(artefact['url'])) as f:
                d['checksum'] = sha256(f.read()).hexdigest()
            logging.debug("Done fetching %s", name)
    else:  # no sdist found
        d['url'] = ''
        d['checksum'] = ''
        warnings.warn("No sdist found for %s" % name)
    d['checksum_type'] = 'sha256'
    return d


def replace_resources_with_brew_output(formula_path, formula_name):
    # Get new resources block from `brew update-python-resources`
    result = subprocess.run(
        ["brew", "update-python-resources", formula_name, "--package-name", formula_name, "--print-only"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        check=True
    )
    new_resources = result.stdout.strip()

    # Read the original formula
    with open(formula_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace from first `resource ...` to (but not including) `def install`
    pattern = re.compile(r'^(\s*resource\b.*?)(?=^(\s*def install\b))', re.DOTALL | re.MULTILINE)

    updated_content = pattern.sub('\n  ' + new_resources.rstrip() + '\n', content, count=1)

    # Write back the updated content
    with open(formula_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

    print("Resource blocks updated in", formula_path)


def replace_url_sha256(filename: str, new_url: str, new_sha256: str):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    url_pattern = re.compile(r'^\s*url\s+["\'].*["\']')
    sha_pattern = re.compile(r'^\s*sha256\s+["\'].*["\']')

    replaced = False
    for i in range(len(lines) - 1):
        if url_pattern.match(lines[i]) and sha_pattern.match(lines[i + 1]):
            lines[i] = f'  url "{new_url}"\n'
            lines[i + 1] = f'  sha256 "{new_sha256}"\n'
            replaced = True
            break

    if not replaced:
        raise ValueError("Could not find url and sha256 lines to replace.")

    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def update_resource_url_sha256(filename: str, resource_name: str, new_url: str, new_sha256: str):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Match the resource block for the given name
    resource_pattern = re.compile(
        rf'(^\s*resource\s+"{re.escape(resource_name)}"\s+do\s*\n)(.*?)(^\s*end\s*$)',
        re.DOTALL | re.MULTILINE
    )

    match = resource_pattern.search(content)
    if not match:
        raise ValueError(f"Resource block for '{resource_name}' not found.")

    resource_header, resource_body, resource_footer = match.groups()

    # Replace url and sha256 lines in the body
    updated_body = re.sub(r'^\s*url\s+".*"', f'    url "{new_url}"', resource_body, flags=re.MULTILINE)
    updated_body = re.sub(r'^\s*sha256\s+".*"', f'    sha256 "{new_sha256}"', updated_body, flags=re.MULTILINE)

    # Combine new resource block
    new_block = f"{resource_header}{updated_body}{resource_footer}"

    # Replace the original block with the updated one
    new_content = content[:match.start()] + new_block + content[match.end():]

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"Updated URL and sha256 for resource '{resource_name}' in {filename}")


if __name__ == '__main__':
    formula_file = sys.argv[1] if len(sys.argv) > 1 else "../Formula/xml2rfc.rb"
    package = "xml2rfc"

    nodes = merge_graphs([make_graph(package) for p in [package, "google-i18n-address"]])
    # Remove package itself and output it under a different marker
    package_node = nodes[package]
    del nodes[package]

    # Ah-hoc patch to force binary package for google-i18n-address.
    # The source package does not work for the formula for some reason
    google_i18n_address = "google-i18n-address"
    i18n_node = nodes[google_i18n_address]
    i18n_binary_node = research_package(google_i18n_address, version=i18n_node['version'], package_type="bdist_wheel")
    if "url" in i18n_binary_node:
        nodes[google_i18n_address] = i18n_binary_node

    # Update formula package
    replace_url_sha256(formula_file, package_node["url"], package_node["checksum"])

    # Update dependencies
    replace_resources_with_brew_output(formula_file, "xml2rfc")

    # Override "google-i18n-address"
    update_resource_url_sha256(formula_file, "google-i18n-address", i18n_binary_node["url"], i18n_binary_node["checksum"])
