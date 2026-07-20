"""
FiberQ - Translation (i18n) support

Loads compiled Qt translation catalogues (``fiberq_<locale>.qm``) that live in
this directory and installs them into the running QGIS application.

This module is deliberately self-contained: it imports **only** from the Qt
bindings (and, optionally, ``qgis.core`` for ``QgsSettings``). It must never
import from ``fiberq.utils`` or any other plugin package, so that it can be
imported from anywhere in the plugin without risking a circular import.

Copyright (C) Vladimir Vukovic
SPDX-License-Identifier: GPL-3.0-or-later

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.
"""

import logging
import os

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator

logger = logging.getLogger(__name__)

# Catalogue files are named "fiberq_<locale>.qm" and live next to this module.
_QM_PREFIX = 'fiberq_'
_QM_SUFFIX = '.qm'

# The plugin's own language preference, written by the toolbar language selector.
# Kept in step with utils.helpers._FIBERQ_LANG_KEY (duplicated deliberately: this
# package must not import from the rest of the plugin).
FIBERQ_LANG_KEY = 'FiberQ/lang'

# Display names for the locales we ship. Unknown codes fall back to the code
# itself, so adding a new .qm file never crashes the language menu.
_LANGUAGE_NAMES = {
    'en': 'English',
    'sr': 'Srpski',
    'fr': 'Français',
    'de': 'Deutsch',
    'es': 'Español',
    'it': 'Italiano',
    'nl': 'Nederlands',
    'pl': 'Polski',
    'pt': 'Português',
    'ru': 'Русский',
}


def _i18n_dir():
    """Absolute path of the directory holding the .qm catalogues."""
    return os.path.dirname(os.path.abspath(__file__))


def _settings():
    """Return a settings object, preferring QgsSettings, or None."""
    try:
        from qgis.core import QgsSettings
        return QgsSettings()
    except ImportError:
        try:
            from qgis.PyQt.QtCore import QSettings
            return QSettings()
        except ImportError:
            logger.warning('FiberQ i18n: no settings backend available; using system locale')
            return None


def current_locale():
    """Return the two-letter locale code the FiberQ UI should use.

    Resolution order:

    1. ``FiberQ/lang`` -- the plugin's own language selector. This wins so that a
       user can run FiberQ in one language while QGIS itself runs in another,
       which is common where the local fibre vocabulary differs from the
       language someone prefers for the rest of the GIS.
    2. ``locale/userLocale`` -- the QGIS-wide language setting.
    3. The system locale.

    Always returns a two-letter lowercase code (e.g. 'en', 'sr').
    """
    settings = _settings()
    value = None

    if settings is not None:
        # FIBERQ_LANG_KEY must stay in step with utils.helpers._FIBERQ_LANG_KEY.
        # It is duplicated rather than imported so that this package keeps zero
        # dependencies on the rest of the plugin -- a circular import here would
        # break plugin loading entirely, not just translation.
        value = settings.value(FIBERQ_LANG_KEY, None)
        if not value:
            value = settings.value('locale/userLocale', None)

    if not value:
        value = QLocale().name()
    return str(value)[0:2].lower()


def qm_path_for(locale, plugin_dir=None):
    """Absolute path of the .qm catalogue for ``locale`` (may not exist)."""
    base = os.path.join(plugin_dir, 'i18n') if plugin_dir else _i18n_dir()
    return os.path.join(base, '{0}{1}{2}'.format(_QM_PREFIX, locale, _QM_SUFFIX))


def install_translator(plugin_dir):
    """Install the translation catalogue matching the current QGIS locale.

    Args:
        plugin_dir: Absolute path of the plugin package directory. The
            catalogue is looked up at ``<plugin_dir>/i18n/fiberq_<locale>.qm``.

    Returns:
        The installed QTranslator, or None when no catalogue exists for the
        current locale (or loading failed).

    Note:
        The caller **must** keep a reference to the returned translator. Qt
        does not take ownership, so a garbage-collected QTranslator silently
        stops translating.
    """
    locale = current_locale()
    qm_file = qm_path_for(locale, plugin_dir)

    if not os.path.exists(qm_file):
        logger.debug('FiberQ i18n: no catalogue for locale %r at %s', locale, qm_file)
        return None

    translator = QTranslator()
    if not translator.load(qm_file):
        logger.warning('FiberQ i18n: failed to load catalogue %s', qm_file)
        return None

    if not QCoreApplication.installTranslator(translator):
        logger.warning('FiberQ i18n: Qt refused to install catalogue %s', qm_file)
        return None

    logger.info('FiberQ i18n: installed catalogue for locale %r', locale)
    return translator


def remove_translator(translator):
    """Uninstall a translator previously returned by install_translator().

    Safe to call with None. Returns True when a translator was removed.
    """
    if translator is None:
        return False
    try:
        QCoreApplication.removeTranslator(translator)
    except RuntimeError as exc:
        # The underlying C++ object may already be gone during plugin reload.
        logger.warning('FiberQ i18n: could not remove translator: %s', exc)
        return False
    return True


def available_languages(plugin_dir=None):
    """Return the sorted locale codes for which a catalogue is on disk.

    'en' is always included: it is the source language of the plugin and needs
    no catalogue.
    """
    base = os.path.join(plugin_dir, 'i18n') if plugin_dir else _i18n_dir()
    codes = {'en'}

    try:
        entries = os.listdir(base)
    except OSError as exc:
        logger.debug('FiberQ i18n: cannot list %s: %s', base, exc)
        return sorted(codes)

    for entry in entries:
        if entry.startswith(_QM_PREFIX) and entry.endswith(_QM_SUFFIX):
            code = entry[len(_QM_PREFIX):-len(_QM_SUFFIX)]
            if code:
                codes.add(code.lower())

    return sorted(codes)


def safe_format(translated, source, **kwargs):
    """Substitute ``kwargs`` into a TRANSLATED format string, without trusting it.

    A translated string is user-supplied data: it arrives from a .ts catalogue
    that a volunteer edited by hand. ``str.format`` raises on a renamed or
    malformed placeholder -- ``"Placer {nom}"`` gives KeyError, a stray brace
    gives ValueError -- and these strings are formatted while the toolbar is
    being built, so an uncaught error takes down plugin loading, not just one
    label.

    Falls back to the untranslated English source, which is under our control
    and always formats. The user sees one English label instead of a plugin
    that will not start.

    Args:
        translated: the localised format string (from tr()).
        source: the original English format string, used as the fallback.
        **kwargs: values to substitute.

    Returns:
        The formatted string; never raises for a bad translation.
    """
    try:
        return translated.format(**kwargs)
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning(
            'FiberQ i18n: broken placeholder in translation %r (%s); '
            'falling back to English. Fix the catalogue entry.', translated, exc)
    try:
        return source.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        # The English source itself is malformed: a real bug, not a translation
        # problem. Return it verbatim rather than raising during GUI construction.
        logger.error('FiberQ i18n: source string %r cannot be formatted', source)
        return source


def language_name(code):
    """Human-readable name for a locale code.

    Unknown codes are returned unchanged rather than raising, so a newly added
    catalogue always shows up in the language menu.
    """
    if not code:
        return ''
    return _LANGUAGE_NAMES.get(str(code).lower(), str(code))
