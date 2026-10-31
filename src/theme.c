#include "theme.h"
#include "session.h"
#include <glib.h>
#include <string.h>

static void color(GKeyFile *file, const char *theme, const char *key, float result[4], const char *fallback)
{
    char *value = g_key_file_get_string(file, theme, key, NULL);
    const char *hex = value;
    bool valid = hex != NULL && strlen(hex) == 7 && hex[0] == '#';
    for (int i = 1; valid && i < 7; ++i) valid = g_ascii_isxdigit(hex[i]);
    if (!valid) hex = fallback;
    for (int i = 0; i < 3; ++i)
        result[i] = (float)(16 * g_ascii_xdigit_value(hex[1+2*i]) + g_ascii_xdigit_value(hex[2+2*i])) / 255.f;
    result[3] = 1;
    g_free(value);
}

void madway_theme_load(struct madway_config *config, const char *name)
{
    GKeyFile *file = g_key_file_new();
    char *executable = g_file_read_link("/proc/self/exe", NULL);
    char *bin = executable != NULL ? g_path_get_dirname(executable) : NULL;
    char *prefix = bin != NULL ? g_path_get_dirname(bin) : NULL;
    char *path = prefix != NULL ? g_build_filename(prefix, "share", "madway", "themes.ini", NULL) : NULL;
    if (path == NULL || !g_key_file_load_from_file(file, path, G_KEY_FILE_NONE, NULL))
        g_key_file_load_from_file(file, MADWAY_THEME_SOURCE, G_KEY_FILE_NONE, NULL);
    const char *theme = name != NULL && g_key_file_has_group(file, name) ? name : "black";
    config->eau_dark = strcmp(theme, "gershwin-dark") == 0;
    config->eau = strcmp(theme, "gershwin") == 0 || config->eau_dark;
    color(file, theme, "surface", config->surface, "#080808");
    color(file, theme, "active", config->active, "#202020");
    color(file, theme, "text", config->text, "#c8c8c8");
    color(file, theme, "muted", config->muted, "#909090");
    color(file, theme, "border", config->border, "#303030");
    color(file, theme, "accent", config->accent, "#b0b0b0");
    g_free(path);g_free(prefix);g_free(bin);g_free(executable);g_key_file_unref(file);
}
