function conky_draw_rect()
    if conky_window == nil then return end

    local w = conky_window.width
    local h = conky_window.height

    -- Wayland: image surface
    local cs = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, w, h)
    local cr = cairo_create(cs)

    cairo_set_source_rgba(cr, 0, 0, 0, 0)
    cairo_paint(cr)

    local rect_w = 260
    local rect_h = 80
    local rect_x = (w - rect_w) / 2
    local rect_y = (h - rect_h) / 2

    cairo_set_source_rgba(cr, 1, 0, 0, 1)
    cairo_rectangle(cr, rect_x, rect_y, rect_w, rect_h)
    cairo_fill(cr)

    cairo_select_font_face(cr, "DejaVu Sans", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, 40)

    local text = "TEST"
    local ext = cairo_text_extents_t:create()
    cairo_text_extents(cr, text, ext)

    local text_x = rect_x + (rect_w - ext.width) / 2 - ext.x_bearing
    local text_y = rect_y + (rect_h - ext.height) / 2 - ext.y_bearing

    cairo_set_source_rgba(cr, 1, 1, 1, 1)
    cairo_move_to(cr, text_x, text_y)
    cairo_show_text(cr, text)

    cairo_destroy(cr)
    cairo_surface_destroy(cs)
end

