cmake_minimum_required(VERSION 3.20)
project(madway VERSION 0.1.0 LANGUAGES C)
set(MADWAY_RELEASE_VERSION "${PROJECT_VERSION}-alpha.1")
include(GNUInstallDirs)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(PkgConfig REQUIRED)
# Target the exact version installed on your system: wlroots-0.20
pkg_check_modules(WLROOTS REQUIRED wlroots-0.20)
pkg_check_modules(WAYLAND_SERVER REQUIRED wayland-server)
pkg_check_modules(XKBCOMMON REQUIRED xkbcommon)
pkg_check_modules(PANGOCAIRO REQUIRED IMPORTED_TARGET pangocairo)
pkg_check_modules(GIO REQUIRED IMPORTED_TARGET gio-2.0)
pkg_check_modules(LIBINPUT REQUIRED IMPORTED_TARGET libinput)
pkg_check_modules(PIXMAN REQUIRED IMPORTED_TARGET pixman-1)
find_program(WAYLAND_SCANNER wayland-scanner REQUIRED)
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/protocols")
set(LAYER_HEADER "${CMAKE_CURRENT_BINARY_DIR}/protocols/wlr-layer-shell-unstable-v1-protocol.h")
add_custom_command(OUTPUT "${LAYER_HEADER}"
    COMMAND "${WAYLAND_SCANNER}" server-header
        "${CMAKE_CURRENT_SOURCE_DIR}/protocols/wlr-layer-shell-unstable-v1.xml" "${LAYER_HEADER}"
    DEPENDS protocols/wlr-layer-shell-unstable-v1.xml VERBATIM)

add_executable(madway
    src/main.c
    src/main.h
    src/view.c
    src/view.h
    src/input.c
    src/input.h
    src/decoration.c
    src/decoration.h
    src/eau.c
    src/eau.h
    src/window.c
    src/window.h
    src/workspace.c
    src/workspace.h
    src/layer.c
    src/layer.h
    src/monitors.c
    src/monitors.h
    src/session.c
    src/session.h
    src/theme.c
    src/theme.h
    src/taskbar.c
    src/taskbar.h
    src/dock.c
    src/dock.h
    src/preview.c
    src/preview.h
    src/devices.c
    src/devices.h
    src/transition.c
    src/transition.h
    src/motion.c
    src/motion.h
    src/animation.c
    src/animation.h
    src/drag.c
    src/drag.h
    src/power.c
    src/power.h
    src/lock.c
    src/lock.h
    "${LAYER_HEADER}"
)
target_compile_definitions(madway PRIVATE WLR_USE_UNSTABLE)
target_compile_definitions(madway PRIVATE MADWAY_VERSION="${MADWAY_RELEASE_VERSION}")
target_compile_definitions(madway PRIVATE
    MADWAY_THEME_SOURCE="${CMAKE_CURRENT_SOURCE_DIR}/share/madway/themes.ini"
    MADWAY_HELPER_SOURCE="${CMAKE_CURRENT_SOURCE_DIR}/scripts/madway-shell"
    MADWAY_HELPER_INSTALLED="${CMAKE_INSTALL_FULL_BINDIR}/madway-shell")

target_link_libraries(madway PRIVATE
    PkgConfig::PANGOCAIRO
    PkgConfig::GIO
    PkgConfig::LIBINPUT
    PkgConfig::PIXMAN
    ${WLROOTS_LIBRARIES}
    ${WAYLAND_SERVER_LIBRARIES}
    ${XKBCOMMON_LIBRARIES}
)

target_include_directories(madway PRIVATE
    "${CMAKE_CURRENT_BINARY_DIR}/protocols"
    ${WLROOTS_INCLUDE_DIRS}
    ${WAYLAND_SERVER_INCLUDE_DIRS}
    ${XKBCOMMON_INCLUDE_DIRS}
)

install(TARGETS madway RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(PROGRAMS scripts/madway-session scripts/madway-shell scripts/madway-panel scripts/madway-script scripts/madway-terminal scripts/madway-screenshot scripts/madway-desktop DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES scripts/madway_power.py scripts/madway_lock.py scripts/madway_wallpaper.py scripts/madway_files.py DESTINATION ${CMAKE_INSTALL_BINDIR})
install(DIRECTORY share/madway DESTINATION ${CMAKE_INSTALL_DATADIR})

# Plasma Login/SDDM's session shell does not evaluate quotes in Exec paths.
if(CMAKE_INSTALL_FULL_BINDIR MATCHES "[ \t\r\n]")
    message(FATAL_ERROR "The native login entry requires an install bindir without whitespace")
endif()
configure_file(share/wayland-sessions/madway.desktop.in madway.desktop @ONLY)

option(MADWAY_BUILD_DEMOSCENE "Build the optional native Wayland demoscene overlay" OFF)
if(MADWAY_BUILD_DEMOSCENE)
    if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extras/demoscene/CMakeLists.txt")
        message(FATAL_ERROR "Demoscenes are local and Git-ignored. Restore extras/demoscene or disable MADWAY_BUILD_DEMOSCENE.")
    endif()
    enable_language(CXX)
    add_subdirectory(extras/demoscene)
endif()
