import urllib.parse
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from database.repo import GroupRepo, SubRepo, SystemRepo
from keyboards.user import (
    groups_list_kb,
    back_to_home,
    settings_countries_kb,
    group_view_kb,
    settings_tags_kb,
)
from handlers.user.states import UserStates
from handlers.user.start import edit_or_answer
from config import config
from utils.qr import QRGenerator

router = Router()


async def get_base_url():
    db_domain = await SystemRepo.get_config("public_domain")
    domain = db_domain if db_domain else config.public_domain
    if domain:
        return f"https://{domain}"
    return f"http://{config.PUBLIC_IP}:{config.WEB_PORT}"


@router.callback_query(F.data == "groups_list")
async def show_groups(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != UserStates.waiting_for_group_name:
        data = await state.get_data()
        last_msg_id = data.get("last_msg_id")
        await state.clear()
        if last_msg_id:
            await state.update_data(last_msg_id=last_msg_id)

    groups = await GroupRepo.get_user_groups(callback.from_user.id)
    text = (
        "📂 <b>Мои Группы</b>\n\n"
        "Создавайте отдельные ссылки подписки с разными наборами стран.\n"
        "<i>Например: «Gaming» (только Германия) или «Work» (Вся Европа).</i>"
    )
    await edit_or_answer(
        callback.message, text, groups_list_kb(groups), state, media_url="video"
    )


@router.callback_query(F.data == "group_create")
async def ask_group_name(callback: CallbackQuery, state: FSMContext):
    await edit_or_answer(
        callback.message,
        "✍️ <b>Создание группы</b>\n\n"
        "Введите название группы (латиницей, без пробелов).\n"
        "<i>Пример: Gaming, UK-Only, MyWork</i>",
        back_to_home(),
        state,
        media_url="video",
    )
    await state.set_state(UserStates.waiting_for_group_name)


@router.message(StateFilter(UserStates.waiting_for_group_name))
async def create_group_finish(message: Message, state: FSMContext):
    try:
        await message.delete()
    except:
        pass

    name = message.text.strip().replace(" ", "_").replace("/", "-")

    if len(name) > 20 or len(name) < 2:
        await edit_or_answer(
            message,
            "⚠️ Название от 2 до 20 символов.",
            back_to_home(),
            state,
            media_url="video",
        )
        return

    if not all(ord(c) < 128 for c in name):
        await edit_or_answer(
            message,
            "⚠️ Используйте только английские буквы.",
            back_to_home(),
            state,
            media_url="video",
        )
        return

    group = await GroupRepo.create_group(message.from_user.id, name, None)
    if not group:
        await edit_or_answer(
            message,
            "⚠️ Группа с таким именем уже существует.",
            back_to_home(),
            state,
            media_url="video",
        )
        return

    await state.set_state(None)
    all_regions = await SubRepo.get_regions()

    await edit_or_answer(
        message,
        f"✅ Группа <b>{name}</b> создана!\nТеперь выберите страны для этой группы.",
        settings_countries_kb(all_regions, None, group.id),
        state,
        media_url="video",
    )


@router.callback_query(F.data.startswith("group_view_"))
async def view_group(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("group_view_")[1])
    groups = await GroupRepo.get_user_groups(callback.from_user.id)
    group = next((g for g in groups if g.id == group_id), None)

    if not group:
        await callback.answer("Группа не найдена", show_alert=True)
        await show_groups(callback, state)
        return

    base = await get_base_url()
    link_url = f"{base}/sub?id={callback.from_user.id}/{group.name}"

    countries_txt = "Все доступные"
    if group.country_filter:
        if group.country_filter == "__EMPTY__":
            countries_txt = "❌ Ничего не выбрано"
        else:
            countries_txt = group.country_filter

    tags_txt = "Нет фильтров"
    if group.tags_filter:
        tags_txt = group.tags_filter

    text = (
        f"📂 Группа: <b>{group.name}</b>\n\n"
        f"🌍 Страны: <b>{countries_txt}</b>\n"
        f"🏷 Теги: <b>{tags_txt}</b>\n\n"
        f"🔗 <b>Ссылка подписки:</b>\n"
        f"<code>{link_url}</code>\n\n"
        f"👇 <i>Используйте кнопки ниже: открыть или скопировать ссылку.</i>"
    )

    await edit_or_answer(
        callback.message,
        text,
        group_view_kb(group.id, link_url),
        state,
        media_url="video",
    )


@router.callback_query(F.data.startswith("group_qr_"))
async def show_group_qr(callback: CallbackQuery):
    group_id = int(callback.data.split("group_qr_")[1])
    groups = await GroupRepo.get_user_groups(callback.from_user.id)
    group = next((g for g in groups if g.id == group_id), None)

    if not group:
        await callback.answer("Группа не найдена", show_alert=True)
        return

    base = await get_base_url()
    link_url = f"{base}/sub?id={callback.from_user.id}/{group.name}"

    qr_file = QRGenerator.generate(link_url)
    await callback.message.answer_photo(
        photo=qr_file,
        caption=f"<b>📱 QR-код для группы: {group.name}</b>\nОтсканируйте его в приложении.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("group_edit_countries_"))
async def edit_group_countries(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("group_edit_countries_")[1])
    groups = await GroupRepo.get_user_groups(callback.from_user.id)
    group = next((g for g in groups if g.id == group_id), None)

    if not group:
        await callback.answer("Группа не найдена")
        return

    all_regions = await SubRepo.get_regions()
    current_filter = None
    if group.country_filter:
        current_filter = group.country_filter.split(",")

    await edit_or_answer(
        callback.message,
        f"🌍 Настройка стран для группы <b>{group.name}</b>\n(✅ = Включено)",
        settings_countries_kb(all_regions, current_filter, group_id),
        state,
        media_url="video",
    )


@router.callback_query(F.data.startswith("g_toggle_country_"))
async def toggle_group_country(callback: CallbackQuery):
    prefix = "g_toggle_country_"
    data = callback.data[len(prefix) :]
    try:
        group_id_str, region = data.split("_", 1)
        group_id = int(group_id_str)
    except ValueError:
        return

    user_id = callback.from_user.id
    groups = await GroupRepo.get_user_groups(user_id)
    group = next((g for g in groups if g.id == group_id), None)
    if not group:
        return

    all_regions = await SubRepo.get_regions()
    current_filter = group.country_filter.split(",") if group.country_filter else None

    if current_filter is None:
        new_filter = [r for r in all_regions if r != region]
    elif current_filter == ["__EMPTY__"]:
        new_filter = [region]
    else:
        new_filter = current_filter.copy()
        if region in new_filter:
            new_filter.remove(region)
        else:
            new_filter.append(region)

    if not new_filter:
        new_filter = ["__EMPTY__"]
    elif set(new_filter) == set(all_regions):
        new_filter = None

    await GroupRepo.update_group_countries(group.id, new_filter)
    await callback.message.edit_reply_markup(
        reply_markup=settings_countries_kb(all_regions, new_filter, group_id)
    )


@router.callback_query(F.data.startswith("g_set_all_on_"))
async def group_set_all_on(callback: CallbackQuery):
    group_id = int(callback.data.split("_")[-1])
    all_regions = await SubRepo.get_regions()
    await GroupRepo.update_group_countries(group_id, None)
    await callback.message.edit_reply_markup(
        reply_markup=settings_countries_kb(all_regions, None, group_id)
    )


@router.callback_query(F.data.startswith("g_set_all_off_"))
async def group_set_all_off(callback: CallbackQuery):
    group_id = int(callback.data.split("_")[-1])
    all_regions = await SubRepo.get_regions()
    await GroupRepo.update_group_countries(group_id, ["__EMPTY__"])
    await callback.message.edit_reply_markup(
        reply_markup=settings_countries_kb(all_regions, ["__EMPTY__"], group_id)
    )


@router.callback_query(F.data.startswith("group_edit_tags_"))
async def edit_group_tags(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("group_edit_tags_")[1])
    groups = await GroupRepo.get_user_groups(callback.from_user.id)
    group = next((g for g in groups if g.id == group_id), None)

    if not group:
        await callback.answer("Группа не найдена")
        return

    tags = group.tags_filter.split(",") if group.tags_filter else []

    await edit_or_answer(
        callback.message,
        f"🏷 Настройка тегов для группы <b>{group.name}</b>\n"
        "Выберите, какие ключи включать.\n\n"
        "✅ = Оставить только эти\n"
        "❌ = Не фильтровать",
        settings_tags_kb(tags, group_id),
        state,
        media_url="video",
    )


@router.callback_query(F.data.startswith("g_toggle_tag_"))
async def toggle_group_tag(callback: CallbackQuery):
    prefix = "g_toggle_tag_"
    data = callback.data[len(prefix) :]
    try:
        group_id_str, tag = data.split("_", 1)
        group_id = int(group_id_str)
    except ValueError:
        return

    groups = await GroupRepo.get_user_groups(callback.from_user.id)
    group = next((g for g in groups if g.id == group_id), None)
    if not group:
        return

    current_tags = group.tags_filter.split(",") if group.tags_filter else []

    if tag in current_tags:
        current_tags.remove(tag)
    else:
        current_tags.append(tag)

    await GroupRepo.update_group_tags(group.id, current_tags)
    await callback.message.edit_reply_markup(
        reply_markup=settings_tags_kb(current_tags, group_id)
    )


@router.callback_query(F.data.startswith("group_delete_"))
async def delete_group(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("group_delete_")[1])
    await GroupRepo.delete_group(group_id)
    await callback.answer("Группа удалена", show_alert=True)
    await show_groups(callback, state)
