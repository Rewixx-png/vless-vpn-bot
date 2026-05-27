import html

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from database.repo import SubRepo
from handlers.admin.utils import admin_edit_or_answer
from keyboards.admin import bulk_blacklist_regions_kb, bulk_blacklist_subs_kb
from utils.reporter import Reporter

router = Router()

ITEMS_PER_PAGE = 20
STATE_SELECTED = "admin_bl_selected_ids"
STATE_REGION = "admin_bl_region"
STATE_PAGE = "admin_bl_page"
STATE_MODE = "admin_bl_mode"

MODE_INCLUDE = "include"
MODE_EXCLUDE = "exclude"


def _parse_selected_ids(raw_value) -> set[int]:
    if not isinstance(raw_value, list):
        return set()

    result = set()
    for item in raw_value:
        try:
            value = int(item)
        except Exception:
            continue
        if value > 0:
            result.add(value)
    return result


def _normalize_mode(raw_mode: str | None) -> str:
    mode = str(raw_mode or "").strip().lower()
    if mode == MODE_EXCLUDE:
        return MODE_EXCLUDE
    return MODE_INCLUDE


async def _get_mode(state: FSMContext) -> str:
    data = await state.get_data()
    return _normalize_mode(data.get(STATE_MODE))


async def _get_selected_ids(state: FSMContext) -> set[int]:
    data = await state.get_data()
    return _parse_selected_ids(data.get(STATE_SELECTED, []))


async def _set_selected_ids(state: FSMContext, selected_ids: set[int]) -> None:
    await state.update_data({STATE_SELECTED: sorted(selected_ids)})


async def _render_regions_menu(
    callback: CallbackQuery,
    state: FSMContext,
    notice: str | None = None,
) -> None:
    regions = await SubRepo.get_regions()
    mode = await _get_mode(state)
    selected_ids = await _get_selected_ids(state)
    selected_count = len(selected_ids)

    mode_caption = (
        "<b>Режим:</b> В ЧС выбранное"
        if mode == MODE_INCLUDE
        else "<b>Режим:</b> Не в ЧС выбранное"
    )

    if not regions:
        text = (
            "<blockquote>🚫 <b>Массовый ЧС</b>\n\n"
            "Сейчас база пуста, выбирать нечего.</blockquote>"
        )
        await admin_edit_or_answer(
            callback,
            state,
            text,
            reply_markup=bulk_blacklist_regions_kb([], selected_count, mode=mode),
        )
        return

    notice_block = f"\n\n{notice}" if notice else ""
    if mode == MODE_INCLUDE:
        flow_text = (
            "1) Выберите регион.\n"
            "2) Отметьте конфиги, которые нужно отправить в ЧС (✅).\n"
            "3) Нажмите «Отправить в ЧС»."
        )
    else:
        flow_text = (
            "1) Выберите регион.\n"
            "2) Отметьте конфиги, которые НЕ нужно отправлять в ЧС (🛡).\n"
            "3) Нажмите «В ЧС всё, кроме выбранного»."
        )

    text = (
        "<blockquote>🚫 <b>Массовый ЧС</b>\n\n"
        f"{mode_caption}\n\n"
        f"{flow_text}\n\n"
        f"Выбрано сейчас: <b>{selected_count}</b>"
        f"{notice_block}</blockquote>"
    )

    await state.update_data({STATE_REGION: None, STATE_PAGE: 0})
    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=bulk_blacklist_regions_kb(regions, selected_count, mode=mode),
    )


async def _render_region_page(
    callback: CallbackQuery,
    state: FSMContext,
    region: str,
    page: int,
) -> None:
    all_subs = await SubRepo.get_subs_by_region(region)
    if not all_subs:
        await callback.answer("В этом регионе конфиги уже отсутствуют", show_alert=True)
        await _render_regions_menu(callback, state)
        return

    total_items = len(all_subs)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    safe_page = max(0, min(page, total_pages - 1))

    start_idx = safe_page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_subs = all_subs[start_idx:end_idx]

    mode = await _get_mode(state)
    selected_ids = await _get_selected_ids(state)
    region_ids = {int(sub.id) for sub in all_subs}
    selected_in_region = len(selected_ids.intersection(region_ids))

    if mode == MODE_INCLUDE:
        mode_line = "<b>Режим:</b> В ЧС выбранное"
        selected_line = f"✅ Выбрано (всего): <b>{len(selected_ids)}</b>"
        hint_line = "Нажимайте на строки ниже, чтобы пометить к отправке в ЧС."
        selected_count_override = len(selected_ids)
    else:
        mode_line = "<b>Режим:</b> Не в ЧС выбранное"
        selected_line = (
            f"🛡 Не отправлять (в регионе): <b>{selected_in_region}</b>"
        )
        hint_line = (
            "Нажимайте на строки ниже, чтобы оставить их вне ЧС. "
            "Остальные уйдут в ЧС."
        )
        selected_count_override = selected_in_region

    text = (
        f"<blockquote>🚫 <b>Массовый ЧС</b>\n\n"
        f"{mode_line}\n"
        f"🌍 Регион: <b>{html.escape(region)}</b>\n"
        f"📋 Ключей: <b>{total_items}</b>\n"
        f"📄 Страница: <b>{safe_page + 1}/{total_pages}</b>\n"
        f"{selected_line}\n\n"
        f"{hint_line}</blockquote>"
    )

    await state.update_data({STATE_REGION: region, STATE_PAGE: safe_page})
    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=bulk_blacklist_subs_kb(
            current_subs,
            safe_page,
            total_pages,
            selected_ids,
            index_offset=start_idx,
            mode=mode,
            total_in_region=total_items,
            selected_count_override=selected_count_override,
        ),
    )


@router.callback_query(F.data == "admin_bulk_blacklist_menu")
async def open_bulk_blacklist_menu(callback: CallbackQuery, state: FSMContext):
    mode = await _get_mode(state)
    await state.update_data({STATE_MODE: mode})
    await _render_regions_menu(callback, state)


@router.callback_query(F.data.startswith("bulk_bl_mode_"))
async def switch_bulk_blacklist_mode(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    mode_raw = callback.data[len("bulk_bl_mode_") :]
    mode = _normalize_mode(mode_raw)

    await state.update_data({STATE_MODE: mode, STATE_SELECTED: []})

    data = await state.get_data()
    region = str(data.get(STATE_REGION, "") or "")
    page = int(data.get(STATE_PAGE, 0) or 0)

    mode_name = "В ЧС выбранное" if mode == MODE_INCLUDE else "Не в ЧС выбранное"
    await callback.answer(f"Режим: {mode_name}")

    if region:
        await _render_region_page(callback, state, region, page)
        return

    await _render_regions_menu(callback, state)


@router.callback_query(F.data.startswith("bulk_bl_region_"))
async def open_bulk_blacklist_region(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    payload = callback.data[len("bulk_bl_region_") :]
    region = payload
    page = 0

    if ":" in payload:
        region, page_str = payload.rsplit(":", 1)
        try:
            page = int(page_str)
        except Exception:
            page = 0

    if not region:
        await _render_regions_menu(callback, state)
        return

    data = await state.get_data()
    prev_region = str(data.get(STATE_REGION, "") or "")
    mode = _normalize_mode(data.get(STATE_MODE))
    if mode == MODE_EXCLUDE and prev_region and prev_region != region:
        await _set_selected_ids(state, set())

    await _render_region_page(callback, state, region, page)


@router.callback_query(F.data.startswith("bulk_bl_page_"))
async def paginate_bulk_blacklist(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    data = await state.get_data()
    region = str(data.get(STATE_REGION, "") or "")
    if not region:
        await _render_regions_menu(callback, state)
        return

    try:
        page = int(callback.data[len("bulk_bl_page_") :])
    except Exception:
        page = 0

    await _render_region_page(callback, state, region, page)


@router.callback_query(F.data.startswith("bulk_bl_toggle_"))
async def toggle_bulk_blacklist_item(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    try:
        sub_id = int(callback.data[len("bulk_bl_toggle_") :])
    except Exception:
        await callback.answer("Некорректный ID", show_alert=True)
        return

    selected_ids = await _get_selected_ids(state)
    if sub_id in selected_ids:
        selected_ids.remove(sub_id)
    else:
        selected_ids.add(sub_id)
    await _set_selected_ids(state, selected_ids)

    data = await state.get_data()
    region = str(data.get(STATE_REGION, "") or "")
    page = int(data.get(STATE_PAGE, 0) or 0)

    if not region:
        await _render_regions_menu(callback, state)
        return

    mode = await _get_mode(state)
    if mode == MODE_EXCLUDE:
        await callback.answer("Обновлен список исключений")
    else:
        await callback.answer(f"Выбрано: {len(selected_ids)}")
    await _render_region_page(callback, state, region, page)


@router.callback_query(F.data == "bulk_bl_clear")
async def clear_bulk_blacklist_selection(callback: CallbackQuery, state: FSMContext):
    await _set_selected_ids(state, set())

    data = await state.get_data()
    region = str(data.get(STATE_REGION, "") or "")
    page = int(data.get(STATE_PAGE, 0) or 0)

    await callback.answer("Выбор очищен")
    if region:
        await _render_region_page(callback, state, region, page)
        return

    await _render_regions_menu(callback, state)


@router.callback_query(F.data == "bulk_bl_submit")
async def submit_bulk_blacklist(callback: CallbackQuery, state: FSMContext):
    if not callback.bot or not callback.from_user:
        return
    mode = await _get_mode(state)
    selected_ids = await _get_selected_ids(state)

    target_ids: list[int] = []
    selected_count = len(selected_ids)
    mode_label = "include"
    region = ""

    if mode == MODE_INCLUDE:
        if not selected_ids:
            await callback.answer("Ничего не выбрано", show_alert=True)
            return
        target_ids = sorted(selected_ids)
        mode_label = MODE_INCLUDE
    else:
        data = await state.get_data()
        region = str(data.get(STATE_REGION, "") or "")
        if not region:
            await callback.answer(
                "Сначала выберите регион для режима исключений",
                show_alert=True,
            )
            return

        region_subs = await SubRepo.get_subs_by_region(region)
        if not region_subs:
            await callback.answer("В регионе нет конфигов", show_alert=True)
            await _render_regions_menu(callback, state)
            return

        region_ids = {int(sub.id) for sub in region_subs}
        keep_ids = selected_ids.intersection(region_ids)
        target_ids = sorted(region_ids.difference(keep_ids))
        selected_count = len(keep_ids)
        mode_label = MODE_EXCLUDE

        if not target_ids:
            await callback.answer("Нечего отправлять в ЧС", show_alert=True)
            return

    moved = await SubRepo.move_subs_to_blacklist(
        target_ids,
        reason="Admin Bulk Blacklist",
    )
    await _set_selected_ids(state, set())

    try:
        scope = f", region={region}" if region else ""
        await Reporter.send_admin_action(
            callback.bot,
            (
                f"Bulk blacklist by admin {callback.from_user.id}: "
                f"mode={mode_label}{scope}, selected={selected_count}, "
                f"to_blacklist={len(target_ids)}, moved={moved}"
            ),
        )
    except Exception:
        pass

    await callback.answer(f"Отправлено в ЧС: {moved}", show_alert=True)
    await _render_regions_menu(
        callback,
        state,
        notice=f"✅ В ЧС отправлено: <b>{moved}</b>",
    )
