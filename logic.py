def calculate_risk_data(deposit, risk_percent, stop_percent, fee_percent=0.1):
    if stop_percent <= 0:
        return 0, 0, 0, 0

    # 1. Считаем риск в $
    cash_risk = deposit * (risk_percent / 100)

    # 2. Считаем объем (Стоп + Комиссия)
    total_loss_factor = (stop_percent + fee_percent) / 100
    volume = cash_risk / total_loss_factor

    # 3. Плечо
    leverage = volume / deposit if deposit > 0 else 0

    # 4. Комиссия в $
    comm_usd = volume * (fee_percent / 100)

    return cash_risk, volume, leverage, comm_usd


def calculate_position_adjustment(
    deposit,
    target_risk_percent,
    current_volume,
    stop_entry_percent,
    stop_now_percent,
    fee_percent=0.0,
    tolerance_cash=1e-9,
):
    """Return robust position-adjustment metrics for in-position mode.

    All percentages are provided as plain percent values, e.g. 1.5 for 1.5%.
    Returns a dict with:
      - target_risk_cash
      - current_risk_cash
      - current_risk_percent
            - effective_entry_loss_percent
            - effective_now_loss_percent
      - target_volume
      - delta_volume
      - delta_abs
      - action in {'add', 'reduce', 'in_limit'}
    """
    dep = float(deposit or 0.0)
    risk_pct = float(target_risk_percent or 0.0)
    cur_vol = float(current_volume or 0.0)
    stop_pct_entry = abs(float(stop_entry_percent or 0.0))
    stop_pct_now = abs(float(stop_now_percent or 0.0))
    fee_pct = max(0.0, float(fee_percent or 0.0))

    if dep <= 0:
        raise ValueError("deposit must be > 0")
    if risk_pct <= 0:
        raise ValueError("target_risk_percent must be > 0")
    if stop_pct_entry <= 0:
        raise ValueError("stop_entry_percent must be > 0")
    if stop_pct_now <= 0:
        raise ValueError("stop_now_percent must be > 0")

    # Existing position risk is fixed by average-entry distance to stop.
    effective_entry_loss_percent = stop_pct_entry + fee_pct
    effective_now_loss_percent = stop_pct_now + fee_pct
    if effective_entry_loss_percent <= 0 or effective_now_loss_percent <= 0:
        raise ValueError("effective loss percent must be > 0")

    target_risk_cash = dep * (risk_pct / 100.0)

    entry_loss_factor = effective_entry_loss_percent / 100.0
    now_loss_factor = effective_now_loss_percent / 100.0

    cur_vol = max(0.0, cur_vol)
    current_risk_cash = cur_vol * entry_loss_factor
    current_risk_percent = (current_risk_cash / dep) * 100.0 if dep > 0 else 0.0

    delta_risk_cash = target_risk_cash - current_risk_cash

    if abs(delta_risk_cash) <= float(tolerance_cash or 0.0):
        action = "in_limit"
        target_volume = cur_vol
        delta_volume = 0.0
        delta_abs = 0.0
    elif delta_risk_cash > 0:
        # To increase risk, new size is added from current price level,
        # therefore we use current distance-to-stop for incremental volume.
        action = "add"
        delta_volume = delta_risk_cash / now_loss_factor
        target_volume = cur_vol + delta_volume
        delta_abs = float(delta_volume)
    else:
        # To reduce risk, we cut existing position whose risk profile
        # is defined by entry-to-stop distance.
        action = "reduce"
        delta_volume = delta_risk_cash / entry_loss_factor
        target_volume = max(0.0, cur_vol + delta_volume)
        delta_abs = float(abs(delta_volume))

    return {
        "target_risk_cash": float(target_risk_cash),
        "current_risk_cash": float(current_risk_cash),
        "current_risk_percent": float(current_risk_percent),
        "effective_entry_loss_percent": float(effective_entry_loss_percent),
        "effective_now_loss_percent": float(effective_now_loss_percent),
        "target_volume": float(target_volume),
        "delta_volume": float(delta_volume),
        "delta_abs": float(delta_abs),
        "action": action,
    }


def smart_format(value, precision=2):
    """Для отображения в окне: пробелы-тысячные и запятая"""
    try:
        format_str = f"{{:,.{precision}f}}"
        return format_str.format(value).replace(",", " ").replace(".", ",")
    except:
        return str(value)


def get_info_html(
    cash_risk,
    leverage,
    comm_usd,
    txt_labels,
    prec_risk=2,
    prec_fee=3,
    prec_lev=1,
    font_size=8,
    dimmed=False,
    fee_enabled=True,
):
    """HTML-блок для калькулятора, принимает txt_labels (словарь текстов)"""
    if dimmed:
        # Затемнённые цвета
        text_color = "#555"
        risk_color = "#555"
        sep_color = "#555"
        comm_color = "#555"
        lev_color = "#555"
    else:
        # Обычные цвета
        text_color = "#888"
        risk_color = "#FF453A"
        sep_color = "#666"
        comm_color = "#4DA3FF"
        lev_color = "#B388FF"

    if fee_enabled:
        comm_value = f"${smart_format(comm_usd, prec_fee)}"
        comm_value_color = comm_color
    else:
        comm_value = txt_labels.get("comm_off", "off")
        comm_value_color = "#555" if dimmed else "#888"

    return f"""
    <div style="line-height: 120%; white-space: nowrap;">
        <span style="color: {text_color}; font-size: {font_size}pt;">{txt_labels['risk_deal']} </span>
        <b style="color: {risk_color}; font-size: {font_size+1}pt;">${smart_format(cash_risk, prec_risk)}</b>
        <span style="color: {sep_color};">  |  </span>
        <span style="color: {text_color}; font-size: {font_size}pt;">{txt_labels['comm']} </span>
        <b style="color: {comm_value_color}; font-size: {font_size}pt; background: transparent;">{comm_value}</b>
        <span style="color: {sep_color};">  |  </span>
        <span style="color: {text_color}; font-size: {font_size}pt;">{txt_labels['lev']} </span>
        <b style="color: {lev_color}; font-size: {font_size}pt; background: transparent;">{smart_format(leverage, prec_lev)}x</b>
    </div>
    """
