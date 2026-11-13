"""One package contract for staging, ZIP creation, and provenance validation."""

PROJECT_FILES = {
    'ern-relics.ini': 'config/ern-relics.ini',
    'nightreign-relics.me3': 'config/nightreign-relics.me3',
    'LICENSE': 'LICENSE',
    'ThirdPartyNotices.txt': 'ThirdPartyNotices.txt',
}
PACKAGE_FILES = frozenset(PROJECT_FILES) | {'ern-relics.dll'}
