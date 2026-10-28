CALIBRATION_RESET_MARKER_KEY = "calibration_reset_marker"
CALIBRATION_RESET_VERSION = 3


def reset_terminal_calibration_state(settings, expected_version=None):
    """Clear all stored calibration points and menu points for a fresh run."""
    if not isinstance(settings, dict):
        return False

    if expected_version is None:
        expected_version = CALIBRATION_RESET_VERSION

    if settings.get(CALIBRATION_RESET_MARKER_KEY) == expected_version:
        return False

    list_keys = (
        "points",
        "calc_points_profit_forge",
        "calc_points_metascalp",
        "calc_points_tigertrade",
        "calc_points_surf",
        "calc_points_vataga",
    )
    dict_keys = (
        "pf_glasses_points",
        "metascalp_glasses_points",
        "tiger_glasses_points",
        "tiger_glasses_open_points",
        "tiger_glasses_close_points",
        "surf_glasses_points",
        "surf_glasses_open_points",
        "surf_glasses_accept_points",
        "vataga_glasses_points",
        "vataga_glasses_open_points",
    )
    value_keys = (
        "tiger_open_point",
        "tiger_close_point",
        "surf_open_point",
        "surf_accept_point",
        "vataga_open_point",
        "cas_p_gear",
        "cas_p_left_scrollbar",
        "cas_p_book",
        "cas_p_scrollbar",
        "cas_p_vol1",
        "cas_p_dist1",
        "cas_p_vol2",
        "cas_p_dist2",
        "cas_p_close_x",
        "cas_p_btn_add",
        "cas_p_btn_del",
        "cas_p_combo_vol",
    )

    for key in list_keys:
        settings[key] = []
    for key in dict_keys:
        settings[key] = {}
    for key in value_keys:
        settings[key] = None

    for key in (
        "auto_dep_api_key",
        "auto_dep_api_secret",
        "auto_dep_api_passphrase",
        "auto_dep_credentials",
        "auto_dep_connected",
        "auto_dep_connected_exchange",
        "auto_dep_connected_market",
    ):
        settings[key] = [] if key == "auto_dep_credentials" else ""

    settings["pf_glasses_count"] = 1
    settings["pf_active_glass"] = 1
    settings["pf_selected_glasses"] = [1]
    settings["pf_show_preview_frames"] = False
    settings[CALIBRATION_RESET_MARKER_KEY] = expected_version
    return True
