import codecs
import json
import logging
import re
import sys
import warnings
from contextlib import closing
from hashlib import sha256
from urllib.request import urlopen

import pkg_resources
from poet import merge_graphs, make_graph, RESOURCE_TEMPLATE, PackageVersionNotFoundWarning
from poet.templates import env


URL_NAME_TEMPLATE = env.from_string("""\
  url "{{ resource.url }}"
  {{ resource.checksum_type }} "{{ resource.checksum }}"
""")

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


def replace_between_markers(filename, new_text, start_marker, end_marker):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = re.compile(rf"({re.escape(start_marker)})(.*?){re.escape(end_marker)}", re.DOTALL)

    replacement = f"{start_marker}\n{new_text}\n{end_marker}"

    new_content = pattern.sub(replacement, content)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(new_content)


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
    if google_i18n_address in nodes.keys():
        i18n_node = nodes[google_i18n_address]
        i18n_binary_node = research_package(google_i18n_address, version=i18n_node['version'], package_type="bdist_wheel")
        print(i18n_binary_node)
        if "url" in i18n_binary_node:
            nodes[google_i18n_address] = i18n_binary_node

    package_text = URL_NAME_TEMPLATE.render(resource=package_node)
    dependency_text = '\n\n'.join([RESOURCE_TEMPLATE.render(resource=node) for node in nodes.values()])

    replace_between_markers(
        filename=formula_file,
        new_text=package_text,
        start_marker="# > updater/main.py formula_url #",
        end_marker="  # < updater/main.py formula_url #"
    )

    replace_between_markers(
        filename=formula_file,
        new_text=dependency_text,
        start_marker="# > updater/main.py formula_dependencies #",
        end_marker="  # < updater/main.py formula_dependencies #"
    )
