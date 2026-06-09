"""
Book routes: catalog, detail, author studio, chapters, reviews.
Mix of HTML pages and JSON API endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_current_user,
    get_current_user_optional,
    get_current_active_author,
    get_current_moderator,
)
from app.db.session import get_db
from app.models.book import BookStatus
from app.models.user import User
from app.schemas.book import BookCreate, BookUpdate, ChapterCreate, ChapterUpdate, ReviewCreate
from app.services.book_service import (
    create_book,
    get_book_by_slug,
    get_book_by_id,
    update_book,
    list_books,
    create_chapter,
    get_chapter,
    update_chapter,
    delete_chapter,
    list_chapters,
    list_genres,
    list_tags,
    create_review,
    list_reviews,
    toggle_bookmark,
    is_bookmarked,
    increment_views,
    get_user_bookmarks,
    upsert_reading_progress,
    get_reading_progress,
    set_reading_status,
    remove_bookmark,
    get_reading_status,
)
from app.templates_env import templates

router = APIRouter(tags=["books"])


# ── Catalog ───────────────────────────────────────────────────────────────────
@router.get("/catalog", response_class=HTMLResponse)
async def catalog(
    request: Request,
    page: int = Query(1, ge=1),
    genre: Optional[str] = Query(None),
    order: str = Query("views_count"),
    search: Optional[str] = Query(None),
    age_rating: Optional[str] = Query(None),
    section: Optional[str] = Query(None),  # "russian" | "foreign"
    current_user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    genres = await list_genres(db)
    from app.models.book import Genre as GenreEnum
    genre_enum = None
    if genre:
        try:
            genre_enum = GenreEnum(genre)
        except ValueError:
            genre_enum = None

    # Usernames of foreign (demo) authors — used for section filtering.
    ENGLISH_USERNAMES = [
        "lewis_carroll", "jane_austen", "arthur_conan_doyle", "bram_stoker",
        "hg_wells", "rl_stevenson", "mary_shelley", "charles_dickens",
        "oscar_wilde", "mark_twain", "jules_verne", "charlotte_bronte",
        "lf_baum", "jack_london", "alexandre_dumas",
    ]

    _PER_PAGE = 18
    if section in ("foreign", "russian"):
        # Push the section filter down to SQL using a JOIN — avoids fetching all books into Python.
        from sqlalchemy import select as _sel, func as _func, or_ as _or
        from sqlalchemy.orm import selectinload as _sload
        from app.models.user import User as _User
        from app.models.book import Book as _Book

        _sort_map = {
            "views_count": _Book.views_count.desc(),
            "likes_count": _Book.likes_count.desc(),
            "rating":      _Book.rating.desc(),
            "created_at":  _Book.created_at.desc(),
            "updated_at":  _Book.updated_at.desc(),
        }
        q = (
            _sel(_Book)
            .join(_User, _Book.author_id == _User.id)
            .where(_Book.is_published == True, _Book.is_draft_hidden == False)
            .options(_sload(_Book.author))
        )
        if genre_enum:
            q = q.where(_Book.genre == genre_enum)
        if search:
            _term = f"%{search}%"
            q = q.where(_or(_Book.title.ilike(_term), _Book.description.ilike(_term)))
        if section == "foreign":
            q = q.where(_User.username.in_(ENGLISH_USERNAMES))
        else:
            q = q.where(_User.username.notin_(ENGLISH_USERNAMES))
        q = q.order_by(_sort_map.get(order, _Book.views_count.desc()))

        count_q = _sel(_func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()
        books = list((await db.execute(
            q.offset((page - 1) * _PER_PAGE).limit(_PER_PAGE)
        )).scalars().all())
    else:
        books, total = await list_books(
            db,
            page=page,
            per_page=_PER_PAGE,
            genre=genre_enum,
            order_by=order,
            search=search,
        )

    import math
    return templates.TemplateResponse(
        "books/catalog.html",
        {
            "request": request,
            "current_user": current_user,
            "books": books,
            "genres": genres,
            "active_genre": genre,
            "active_order": order,
            "search": search or "",
            "total": total,
            "page": page,
            "pages": math.ceil(total / _PER_PAGE) or 1,
            "active_section": section or "",
        },
    )


# ── Book detail ───────────────────────────────────────────────────────────────
@router.get("/books/{slug}", response_class=HTMLResponse)
async def book_detail(
    request: Request,
    slug: str,
    current_user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_slug(db, slug)
    _public_statuses = (BookStatus.ONGOING, BookStatus.COMPLETED, BookStatus.HIATUS)
    if not book or (
        (book.status not in _public_statuses or not book.is_published)
        and (not current_user or (current_user.id != book.author_id and not current_user.is_staff))
    ):
        raise HTTPException(404, "Book not found")

    chapters = await list_chapters(db, book.id, published_only=True)
    reviews, rev_total = await list_reviews(db, book.id)
    bookmarked = False
    reading_status = None
    progress = None
    user_review = None
    if current_user:
        bookmarked = await is_bookmarked(db, current_user.id, book.id)
        reading_status = await get_reading_status(db, current_user.id, book.id)
        progress = await get_reading_progress(db, current_user.id, book.id)
        from app.services.book_service import get_user_review
        user_review = await get_user_review(db, current_user.id, book.id)

    subscribed = False
    if current_user:
        from app.services.book_service import is_subscribed_to_book
        subscribed = await is_subscribed_to_book(db, current_user.id, book.id)

    await increment_views(db, book.id)

    return templates.TemplateResponse(
        "books/detail.html",
        {
            "request": request,
            "current_user": current_user,
            "book": book,
            "chapters": chapters,
            "reviews": reviews,
            "rev_total": rev_total,
            "bookmarked": bookmarked,
            "reading_status": reading_status,
            "progress": progress,
            "user_review": user_review,
            "subscribed": subscribed,
        },
    )


# ── Chapter reader ────────────────────────────────────────────────────────────
@router.get("/books/{slug}/chapters/{chapter_num}", response_class=HTMLResponse)
async def read_chapter(
    request: Request,
    slug: str,
    chapter_num: int,
    current_user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_slug(db, slug)
    if not book:
        raise HTTPException(404, "Book not found")

    chapters = await list_chapters(db, book.id, published_only=True)
    chapter = next((c for c in chapters if c.number == chapter_num), None)
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    # Track reading progress
    if current_user:
        await upsert_reading_progress(db, current_user.id, book.id, chapter.id)

    prev_ch = next((c for c in chapters if c.number == chapter_num - 1), None)
    next_ch = next((c for c in chapters if c.number == chapter_num + 1), None)

    return templates.TemplateResponse(
        "books/reader.html",
        {
            "request": request,
            "current_user": current_user,
            "book": book,
            "chapter": chapter,
            "chapters": chapters,
            "prev_chapter": prev_ch,
            "next_chapter": next_ch,
            "progress_pct": round(((next((i for i, c in enumerate(chapters) if c.number == chapter_num), 0) + 1) / len(chapters)) * 100) if chapters else 0,
            "bookmarked": await is_bookmarked(db, current_user.id, book.id) if current_user else False,
        },
    )


# ── Author studio — new book form ─────────────────────────────────────────────
@router.get("/write/new", response_class=HTMLResponse)
async def new_book_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.can_publish:
        return RedirectResponse("/", status_code=302)
    genres = await list_genres(db)
    tags = await list_tags(db)
    return templates.TemplateResponse(
        "books/editor.html",
        {
            "request": request,
            "current_user": current_user,
            "genres": genres,
            "tags": tags,
            "book": None,
        },
    )


@router.post("/write/new")
async def create_new_book(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    genre: str = Form("fantasy"),
    direction: str = Form("gen"),
    is_adult: bool = Form(False),
    tags_json: str = Form("[]"),
    spoiler_tags_json: str = Form("[]"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import json as _json
    if not current_user.can_publish and current_user.role.value == "reader":
        return RedirectResponse("/", status_code=302)
    if not current_user.can_publish:
        # Auto-promote readers who try to publish
        from app.services.user_service import set_role
        from app.models.user import UserRole
        await set_role(db, current_user, UserRole.AUTHOR)

    from app.models.book import Genre as GenreEnum
    try:
        genre_enum = GenreEnum(genre)
    except ValueError:
        genre_enum = GenreEnum.FANTASY
    data = BookCreate(
        title=title,
        description=description or None,
        genre=genre_enum,
        cover_emoji="",
    )
    book = await create_book(db, current_user, data)
    # Set direction and is_adult
    book.direction = direction
    book.is_adult = is_adult
    # Collect content warnings
    form_data = await request.form()
    warnings = [k[8:] for k in form_data.keys() if k.startswith('warning_')]
    book.content_warnings = _json.dumps(warnings) if warnings else None
    await db.flush()
    # Add tags
    try:
        tag_names = _json.loads(tags_json or "[]")
        if tag_names:
            from app.services.book_service import add_tags_to_book
            await add_tags_to_book(db, book.id, tag_names)
    except Exception:
        pass
    return RedirectResponse(f"/write/{book.id}/chapters/new", status_code=302)


# ── Author studio — edit book ─────────────────────────────────────────────────
@router.get("/write/{book_id}", response_class=HTMLResponse)
async def edit_book_page(
    request: Request,
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_id(db, book_id, load_relations=True)
    if not book:
        raise HTTPException(404)
    if book.author_id != current_user.id and not current_user.is_staff:
        raise HTTPException(403)
    genres = await list_genres(db)
    tags = await list_tags(db)
    chapters = await list_chapters(db, book.id, published_only=False)
    return templates.TemplateResponse(
        "books/editor.html",
        {
            "request": request,
            "current_user": current_user,
            "book": book,
            "genres": genres,
            "tags": tags,
            "chapters": chapters,
        },
    )


@router.post("/write/{book_id}")
async def update_book_handler(
    request: Request,
    book_id: int,
    title: str = Form(...),
    description: str = Form(""),
    genre: str = Form("fantasy"),
    direction: str = Form("gen"),
    status: str = Form("draft"),
    tags_json: str = Form(""),
    spoiler_tags_json: str = Form("[]"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import json as _json
    book = await get_book_by_id(db, book_id)
    if not book or (book.author_id != current_user.id and not current_user.is_staff):
        raise HTTPException(403)
    from app.models.book import Genre as GenreEnum
    try:
        genre_enum = GenreEnum(genre)
    except ValueError:
        genre_enum = None
    try:
        status_enum = BookStatus(status)
    except ValueError:
        status_enum = BookStatus.DRAFT
    data = BookUpdate(
        title=title,
        description=description or None,
        genre=genre_enum,
        cover_emoji=None,
        status=status_enum,
    )
    # Update direction + is_adult + publish flag (reuse the already-fetched book object)
    book_obj = book
    old_status = book_obj.status
    if book_obj:
        if direction:
            book_obj.direction = direction
        form_data_peek = await request.form()
        book_obj.is_adult = bool(form_data_peek.get('is_adult'))
        # Auto-set is_published when status is ongoing or completed
        if status_enum in (BookStatus.ONGOING, BookStatus.COMPLETED):
            book_obj.is_published = True
            if not current_user.can_publish:
                from app.services.user_service import set_role
                from app.models.user import UserRole
                await set_role(db, current_user, UserRole.AUTHOR)
        elif status_enum == BookStatus.DRAFT:
            book_obj.is_published = False
        await db.flush()
    form_data = form_data_peek  # reuse for warnings below
    # Save content warnings from all checked checkboxes
    if book_obj:
        warnings = [k[8:] for k in form_data.keys() if k.startswith('warning_')]
        book_obj.content_warnings = _json.dumps(warnings) if warnings else None
        await db.flush()
    # Update tags if provided
    if tags_json is not None:
        try:
            tag_names = _json.loads(tags_json) if tags_json else []
            spoiler_names = _json.loads(spoiler_tags_json) if spoiler_tags_json else []
            from app.services.book_service import add_tags_to_book, clear_book_tags
            await clear_book_tags(db, book_id)
            if tag_names or spoiler_names:
                await add_tags_to_book(db, book_id, tag_names, spoiler_names)
        except Exception:
            pass
    updated = await update_book(db, book, data)
    # Notify subscribers if the book status changed
    if book_obj and old_status != status_enum:
        try:
            from app.services.book_service import notify_book_subscribers, STATUS_LABELS_RU
            new_status_label = STATUS_LABELS_RU.get(status_enum.value, status_enum.value)
            await notify_book_subscribers(
                db,
                book_obj,
                kind="book_status",
                title=f"Обновление книги «{updated.title}»",
                body=f"Статус книги изменён на «{new_status_label}»",
                link=f"/books/{updated.slug}",
            )
        except Exception:
            pass
    return RedirectResponse(f"/books/{updated.slug}", status_code=302)


# ── New Chapter ───────────────────────────────────────────────────────────────
@router.get("/write/{book_id}/chapters/new", response_class=HTMLResponse)
async def new_chapter_page(
    request: Request,
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_id(db, book_id)
    if not book or (book.author_id != current_user.id and not current_user.is_staff):
        raise HTTPException(403)
    return templates.TemplateResponse(
        "books/chapter_editor.html",
        {
            "request": request,
            "current_user": current_user,
            "book": book,
            "chapter": None,
        },
    )


@router.post("/write/{book_id}/chapters/new")
async def create_new_chapter(
    request: Request,
    book_id: int,
    title: str = Form(...),
    content: str = Form(...),
    author_note: str = Form(""),
    is_published: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_id(db, book_id)
    if not book or (book.author_id != current_user.id and not current_user.is_staff):
        raise HTTPException(403)
    data = ChapterCreate(
        title=title,
        content=content,
        author_note=author_note or None,
        is_published=is_published,
    )
    chapter = await create_chapter(db, book, data)
    # Auto-publish the book when its first chapter goes live
    if is_published and not book.is_published:
        book.is_published = True
        if book.status == BookStatus.DRAFT:
            book.status = BookStatus.ONGOING
        await db.flush()
    # Notify subscribers about the new chapter if it's published
    if is_published:
        from app.services.book_service import notify_book_subscribers
        await notify_book_subscribers(
            db,
            book,
            kind="new_chapter",
            title=f"Новая глава в «{book.title}»",
            body=f"Опубликована новая глава: «{title}»",
            link=f"/books/{book.slug}/chapters/{chapter.number}",
        )
    return RedirectResponse(f"/write/{book_id}", status_code=302)


# ── Edit Chapter ──────────────────────────────────────────────────────────────
@router.get("/write/{book_id}/chapters/{chapter_id}", response_class=HTMLResponse)
async def edit_chapter_page(
    request: Request,
    book_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_id(db, book_id)
    chapter = await get_chapter(db, chapter_id)
    if not book or not chapter or chapter.book_id != book_id:
        raise HTTPException(404)
    if book.author_id != current_user.id and not current_user.is_staff:
        raise HTTPException(403)
    return templates.TemplateResponse(
        "books/chapter_editor.html",
        {
            "request": request,
            "current_user": current_user,
            "book": book,
            "chapter": chapter,
        },
    )


@router.post("/write/{book_id}/chapters/{chapter_id}")
async def update_chapter_handler(
    request: Request,
    book_id: int,
    chapter_id: int,
    title: str = Form(...),
    content: str = Form(...),
    author_note: str = Form(""),
    is_published: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_id(db, book_id)
    chapter = await get_chapter(db, chapter_id)
    if not book or not chapter or chapter.book_id != book_id:
        raise HTTPException(404)
    if book.author_id != current_user.id and not current_user.is_staff:
        raise HTTPException(403)
    was_published = chapter.is_published
    data = ChapterUpdate(
        title=title,
        content=content,
        author_note=author_note or None,
        is_published=is_published,
    )
    await update_chapter(db, chapter, data)
    # Auto-publish the book when a chapter is published for the first time
    if is_published and not was_published and not book.is_published:
        book.is_published = True
        if book.status == BookStatus.DRAFT:
            book.status = BookStatus.ONGOING
        await db.flush()
    # Notify subscribers if chapter was just published for the first time
    if is_published and not was_published:
        try:
            from app.services.book_service import notify_book_subscribers
            await notify_book_subscribers(
                db,
                book,
                kind="new_chapter",
                title=f"Новая глава в «{book.title}»",
                body=f"Опубликована новая глава: «{title}»",
                link=f"/books/{book.slug}/chapters/{chapter.number}",
            )
        except Exception:
            pass
    return RedirectResponse(f"/write/{book_id}", status_code=302)


# ── Reviews (JSON API) ────────────────────────────────────────────────────────
@router.post("/api/books/{book_id}/reviews", response_class=JSONResponse)
async def post_review(
    book_id: int,
    data: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(404)
    try:
        review = await create_review(db, current_user, book, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Notify book author if they have comment notifications enabled
    if book.author_id != current_user.id:
        try:
            from app.models.user import User as UserModel
            from app.models.social import Notification
            from sqlalchemy import select as _sel
            author = (await db.execute(_sel(UserModel).where(UserModel.id == book.author_id))).scalar_one_or_none()
            if author and author.notify_comments:
                reviewer_name = current_user.display_name or current_user.username
                db.add(Notification(
                    user_id=author.id,
                    kind="review",
                    title=f"Новый отзыв на «{book.title}»",
                    body=f"{reviewer_name} оставил(а) отзыв на вашу книгу",
                    link=f"/books/{book.slug}#reviews",
                ))
                await db.flush()
        except Exception:
            pass
    return {"id": review.id, "rating": review.rating, "message": "Review submitted"}


# ── Bookmark toggle (JSON API) ─────────────────────────────────────────────────
@router.post("/api/books/{book_id}/bookmark", response_class=JSONResponse)
async def bookmark_book(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(404)
    added = await toggle_bookmark(db, current_user.id, book_id)
    # toggle_bookmark already updates bookmarks_count, refetch the book
    book = await get_book_by_id(db, book_id)
    return {"bookmarked": added, "count": book.bookmarks_count if book else 0}


# ── Delete chapter ───────────────────────────────────────────────────────────
@router.post("/write/{book_id}/chapters/{chapter_id}/delete")
async def delete_chapter_handler(
    book_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.chapter import Chapter
    from sqlalchemy import select as sel_ch
    book = await get_book_by_id(db, book_id)
    if not book or (book.author_id != current_user.id and not current_user.is_staff):
        raise HTTPException(403)
    chapter = (await db.execute(
        sel_ch(Chapter).where(Chapter.id == chapter_id, Chapter.book_id == book_id)
    )).scalar_one_or_none()
    if not chapter:
        raise HTTPException(404)
    await delete_chapter(db, chapter, book)
    return RedirectResponse(f"/write/{book_id}", status_code=302)


# ── Report a book ─────────────────────────────────────────────────────────────
@router.post("/api/books/{book_id}/report", response_class=JSONResponse)
async def report_book(
    book_id: int,
    reason: str = "spam",
    comment: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.social import Report
    from sqlalchemy import select
    book = await get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(404)
    existing = (await db.execute(
        select(Report).where(Report.reporter_id == current_user.id, Report.book_id == book_id, Report.is_resolved == False)
    )).scalar_one_or_none()
    if existing:
        return {"message": "Жалоба уже подана"}
    report = Report(reporter_id=current_user.id, book_id=book_id, reason=reason, comment=comment or None)
    db.add(report)
    await db.flush()
    return {"message": "Жалоба принята"}


# ── Notifications API ─────────────────────────────────────────────────────────
@router.get("/api/notifications")
async def get_my_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.social import Notification
    from sqlalchemy import select, func as _func
    notifs = list((await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(20)
    )).scalars())
    # Count total unread separately — not just from the last 20
    unread = (await db.execute(
        select(_func.count()).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )).scalar_one()
    return {
        "unread": unread,
        "items": [{
            "id": n.id, "kind": n.kind, "title": n.title,
            "body": n.body, "link": n.link, "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        } for n in notifs]
    }


@router.post("/api/notifications/{notif_id}/read")
async def mark_notification_read(
    notif_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.social import Notification
    from sqlalchemy import select
    result = await db.execute(
        select(Notification).where(Notification.id == notif_id, Notification.user_id == current_user.id)
    )
    notif = result.scalar_one_or_none()
    if notif:
        notif.is_read = True
        await db.flush()
    return {"ok": True}


@router.post("/api/notifications/read-all")
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.social import Notification
    from sqlalchemy import update
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    return {"ok": True}


# ── Hide/unhide book (author) ─────────────────────────────────────────────────
@router.post("/api/books/{book_id}/toggle-visibility", response_class=JSONResponse)
async def toggle_book_visibility(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(404)
    if book.author_id != current_user.id and not current_user.is_staff:
        raise HTTPException(403)
    book.is_draft_hidden = not book.is_draft_hidden
    await db.flush()
    return {"hidden": book.is_draft_hidden}


# ── Hide/unhide chapter (author) ──────────────────────────────────────────────
@router.post("/api/chapters/{chapter_id}/toggle-visibility", response_class=JSONResponse)
async def toggle_chapter_visibility(
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.chapter import Chapter
    from sqlalchemy import select as sel
    result = await db.execute(sel(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(404)
    book = await get_book_by_id(db, chapter.book_id)
    if not book or (book.author_id != current_user.id and not current_user.is_staff):
        raise HTTPException(403)
    chapter.is_draft_hidden = not chapter.is_draft_hidden
    await db.flush()
    return {"hidden": chapter.is_draft_hidden}


@router.post("/api/books/{book_id}/chapters/reorder", response_class=JSONResponse)
async def reorder_chapters(
    book_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-reorder chapters by submitting the full ordered list of chapter IDs."""
    from app.models.chapter import Chapter
    from sqlalchemy import select as _sel
    book = await get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(404)
    if book.author_id != current_user.id and not current_user.is_staff:
        raise HTTPException(403)
    data = await request.json()
    order: list = data.get("order", [])
    if not order:
        raise HTTPException(400, "Empty order")
    chapters = (await db.execute(_sel(Chapter).where(Chapter.book_id == book_id))).scalars().all()
    ch_map = {ch.id: ch for ch in chapters}
    # Two-pass to avoid UniqueConstraint(book_id, number) violation during flush.
    # First pass: assign high temp numbers (>10000) that won't collide with real ones.
    for idx, ch_id in enumerate(order, start=1):
        if ch_id in ch_map:
            ch_map[ch_id].number = 10000 + idx
    await db.flush()
    # Second pass: assign final numbers.
    for idx, ch_id in enumerate(order, start=1):
        if ch_id in ch_map:
            ch_map[ch_id].number = idx
    await db.flush()
    return {"ok": True}


@router.post("/api/chapters/{chapter_id}/delete", response_class=JSONResponse)
async def delete_chapter_api(
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.chapter import Chapter
    from sqlalchemy import select as sel_
    chapter = (await db.execute(sel_(Chapter).where(Chapter.id == chapter_id))).scalar_one_or_none()
    if not chapter:
        raise HTTPException(404)
    book = await get_book_by_id(db, chapter.book_id)
    if not book or (book.author_id != current_user.id and not current_user.is_staff):
        raise HTTPException(403)
    await delete_chapter(db, chapter, book)
    return {"ok": True}


# ── Subscribe to book (JSON API) ──────────────────────────────────────────────
@router.post("/api/books/{book_id}/subscribe", response_class=JSONResponse)
async def subscribe_to_book(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.book_service import toggle_book_subscription, get_book_by_id
    book = await get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(404)
    subscribed = await toggle_book_subscription(db, current_user.id, book_id)
    return {"subscribed": subscribed}


# ── Reading status (shelf) ────────────────────────────────────────────────────
@router.post("/api/books/{book_id}/reading-status", response_class=JSONResponse)
async def set_book_reading_status(
    book_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set reading status: reading | will_read | read | dropped. Empty/remove removes bookmark."""
    body = await request.json()
    status = body.get("status", "")
    book = await get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(404)
    if status == "remove" or not status:
        removed = await remove_bookmark(db, current_user.id, book_id)
        book = await get_book_by_id(db, book_id)
        return {"bookmarked": False, "status": None, "count": book.bookmarks_count if book else 0}
    new_status = await set_reading_status(db, current_user.id, book_id, status)
    book = await get_book_by_id(db, book_id)
    return {"bookmarked": True, "status": new_status, "count": book.bookmarks_count if book else 0}
