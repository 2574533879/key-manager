"""
Generate a minimal Tailwind-compatible CSS file.
Zero dependencies — uses only Python stdlib.
Run once, commit the output CSS. Re-run when templates change.
"""
import re, os

# ── Tailwind default design tokens ────────────────
COLORS = {
    "white": "#fff", "black": "#000", "transparent": "transparent",
    "gray-50": "#f9fafb", "gray-100": "#f3f4f6", "gray-300": "#d1d5db",
    "gray-400": "#9ca3af", "gray-500": "#6b7280", "gray-600": "#4b5563",
    "gray-700": "#374151", "gray-800": "#1f2937", "gray-900": "#111827",
    "red-50": "#fef2f2", "red-200": "#fecaca", "red-500": "#ef4444",
    "red-600": "#dc2626", "red-700": "#b91c1c",
    "blue-50": "#eff6ff", "blue-100": "#dbeafe", "blue-200": "#bfdbfe",
    "blue-500": "#3b82f6", "blue-600": "#2563eb", "blue-800": "#1e40af",
    "green-50": "#f0fdf4", "green-500": "#22c55e", "green-600": "#16a34a",
    "green-700": "#15803d", "green-800": "#166534",
    "yellow-50": "#fefce8", "yellow-500": "#eab308", "yellow-600": "#ca8a04",
    "purple-600": "#9333ea",
    "orange-50": "#fff7ed", "orange-600": "#ea580c",
}
SPACING = {  # key: rem
    "0": "0", "px": "1px", "0.5": "0.125rem", "1": "0.25rem", "1.5": "0.375rem",
    "2": "0.5rem", "2.5": "0.625rem", "3": "0.75rem", "4": "1rem",
    "5": "1.25rem", "6": "1.5rem", "8": "2rem", "12": "3rem",
}
WIDTHS = {**SPACING, "10": "2.5rem", "20": "5rem", "32": "8rem",
          "40": "10rem", "48": "12rem", "56": "14rem",
          "full": "100%", "screen": "100vh", "auto": "auto"}
MAXW = {"xs": "20rem", "sm": "24rem", "md": "28rem", "lg": "32rem",
        "xl": "36rem", "4xl": "56rem"}
FONTS = {"xs": ["0.75rem", "1rem"], "sm": ["0.875rem", "1.25rem"],
         "lg": ["1.125rem", "1.75rem"], "xl": ["1.25rem", "1.75rem"],
         "2xl": ["1.5rem", "2rem"]}

out = []

def css(selector, **props):
    rules = ";".join(f"{k.replace('_','-')}:{v}" for k, v in props.items())
    out.append(f"{selector}{{{rules}}}")

# ── Preflight ─────────────────────────────────────
out.append("*,::before,::after{box-sizing:border-box;border-width:0;border-style:solid;border-color:#e5e7eb}")
out.append("html{-webkit-text-size-adjust:100%;tab-size:4;font-family:Inter,ui-sans-serif,system-ui,sans-serif;line-height:1.5}")
out.append("body{margin:0;line-height:inherit}")
out.append("h1,h2,h3,p{margin:0}")
out.append("a{color:inherit;text-decoration:inherit}")
out.append("table{text-indent:0;border-collapse:collapse}")
out.append("button,input,select,textarea{font-family:inherit;font-size:100%;font-weight:inherit;line-height:inherit;color:inherit;margin:0;padding:0}")

# ── Layout ────────────────────────────────────────
DISPLAY_MAP = {"block": "block", "inline-block": "inline-block", "inline": "inline",
                "flex": "flex", "grid": "grid", "hidden": "none"}
for c, d in DISPLAY_MAP.items():
    css(f".{c}", display=d)
css(".flex-col", flex_direction="column")
css(".flex-wrap", flex_wrap="wrap")
css(".flex-1", flex="1 1 0%")
css(".shrink-0", flex_shrink="0")
css(".items-start", align_items="flex-start")
css(".items-center", align_items="center")
css(".justify-end", justify_content="flex-end")
css(".justify-center", justify_content="center")
css(".justify-between", justify_content="space-between")
css(".self-end", align_self="flex-end")
for n in [1, 2, 3]:
    css(f".grid-cols-{n}", grid_template_columns=f"repeat({n},minmax(0,1fr))")
css(".col-span-full", grid_column="1/-1")
# Responsive grid columns
for bp, px in [("md", "768px"), ("lg", "1024px")]:
    for n in [2, 3, 4, 6, 7]:
        out.append(f"@media(min-width:{px}){{.{bp}\\:grid-cols-{n}{{grid-template-columns:repeat({n},minmax(0,1fr))}}}}")
for s, v in [("1","0.25rem"),("3","0.75rem"),("4","1rem"),("6","1.5rem")]:
    css(f".space-y-{s}>*+*", margin_top=v)
for s, v in SPACING.items():
    if s in ("0","px","0.5","1","1.5","2","2.5","3","4","5","6","8","12"):
        css(f".gap-{s}", gap=v)

# ── Spacing ───────────────────────────────────────
for k, v in SPACING.items():
    for pre, prop in [("p","padding"),("px","padding-left;padding-right"),
                      ("py","padding-top;padding-bottom"),("m","margin"),
                      ("mt","margin-top"),("mb","margin-bottom"),
                      ("ml","margin-left"),("mr","margin-right")]:
        if k not in ("0","px","0.5","1","1.5","2","2.5","3","4","5","6","8","12"):
            continue
        sel = f".{pre}-{k}"
        if pre in ("px","py"):
            a, b = prop.split(";")
            css(sel, **{a: v, b: v})
        elif pre == "p":
            if k == "2": css(sel, padding=v)
            elif k == "3": css(sel, padding=v)
            elif k == "4": css(sel, padding=v)
            elif k == "6": css(sel, padding=v)
            elif k == "8": css(sel, padding=v)
        else:
            css(sel, **{prop: v})

# Special padding values used in templates
css(".py-1\\.5", padding_top="0.375rem", padding_bottom="0.375rem")
css(".py-2\\.5", padding_top="0.625rem", padding_bottom="0.625rem")
css(".py-12", padding_top="3rem", padding_bottom="3rem")
css(".pt-4", padding_top="1rem")
css(".p-3", padding="0.75rem")
css(".p-4", padding="1rem")
css(".px-3", padding_left="0.75rem", padding_right="0.75rem")
css(".px-5", padding_left="1.25rem", padding_right="1.25rem")

# ── Sizing ────────────────────────────────────────
for w, v in WIDTHS.items():
    if w in ("2","3","8","10","20","32","40","48","56","full"):
        css(f".w-{w}", width=v)
for h, v in [("2","0.5rem"),("3","0.75rem"),("8","2rem"),("48","12rem"),("screen","100vh")]:
    css(f".h-{h}", height=v)
css(".min-h-screen", min_height="100vh")
for k, v in MAXW.items():
    css(f".max-w-{k}", max_width=v)
css(".max-h-\\[80vh\\]", max_height="80vh")

# ── Typography ────────────────────────────────────
for s, (sz, lh) in FONTS.items():
    css(f".text-{s}", font_size=sz, line_height=lh)
css(".text-sm", font_size="0.875rem", line_height="1.25rem")
css(".text-lg", font_size="1.125rem", line_height="1.75rem")
css(".text-xl", font_size="1.25rem", line_height="1.75rem")
css(".text-2xl", font_size="1.5rem", line_height="2rem")
for w, v in [("medium","500"),("semibold","600"),("bold","700")]:
    css(f".font-{w}", font_weight=v)
css(".tracking-widest", letter_spacing="0.1em")
for a in ["left", "center", "right"]:
    css(f".text-{a}", text_align=a)
css(".uppercase", text_transform="uppercase")
css(".truncate", overflow="hidden", text_overflow="ellipsis", white_space="nowrap")
css(".select-all", user_select="all")

# ── Colors ────────────────────────────────────────
for name, hex in COLORS.items():
    css(f".text-{name}", color=hex)
    css(f".bg-{name}", background_color=hex)
    css(f".border-{name}", border_color=hex)
# Special: bg-black/40
css(".bg-black\\/40", background_color="rgb(0 0 0 / 0.4)")

# ── Borders ───────────────────────────────────────
css(".border", border_width="1px")
css(".border-0", border_width="0")
css(".border-b", border_bottom_width="1px")
css(".border-t", border_top_width="1px")
css(".border-l-4", border_left_width="4px")
for r, v in {"": "0.25rem", "-lg": "0.5rem", "-xl": "0.75rem", "-full": "9999px"}.items():
    css(f".rounded{r}", border_radius=v)
css(".divide-y>*+*", border_top_width="1px")
css(".divide-gray-100>*+*", border_color="#f3f4f6")

# ── Shadows ───────────────────────────────────────
css(".shadow", box_shadow="0 1px 3px 0 rgb(0 0 0 / 0.1)")
css(".shadow-md", box_shadow="0 4px 6px -1px rgb(0 0 0 / 0.1)")
css(".shadow-lg", box_shadow="0 10px 15px -3px rgb(0 0 0 / 0.1)")
css(".shadow-xl", box_shadow="0 20px 25px -5px rgb(0 0 0 / 0.1)")

# ── Position ──────────────────────────────────────
for p in ["relative", "absolute", "fixed"]:
    css(f".{p}", position=p)
css(".inset-0", top="0", right="0", bottom="0", left="0")
css(".top-4", top="1rem")
css(".right-4", right="1rem")
css(".z-50", z_index="50")

# ── Overflow ──────────────────────────────────────
for o in ["auto", "hidden"]:
    css(f".overflow-{o}", overflow=o)
css(".overflow-x-auto", overflow_x="auto")

# ── Hover / Focus ─────────────────────────────────
css(".hover\\:bg-gray-50:hover", background_color="#f9fafb")
css(".hover\\:bg-gray-800:hover", background_color="#1f2937")
css(".hover\\:bg-green-800:hover", background_color="#166534")
css(".hover\\:bg-red-700:hover", background_color="#b91c1c")
css(".hover\\:text-white:hover", color="#fff")
css(".hover\\:text-gray-600:hover", color="#4b5563")
css(".hover\\:underline:hover", text_decoration="underline")
css(".focus\\:outline-none:focus", outline="2px solid transparent", outline_offset="2px")
css(".focus\\:ring-2:focus", box_shadow="0 0 0 2px #fff, 0 0 0 4px #3b82f6")
css(".focus\\:border-transparent:focus", border_color="transparent")

# ── Misc ──────────────────────────────────────────
css(".transition", transition_property="color,background-color,border-color,text-decoration-color,fill,stroke,opacity,box-shadow,transform,filter,backdrop-filter", transition_duration="150ms")
css(".opacity-40", opacity="0.4")
css(".cursor-pointer", cursor="pointer")
css(".font-mono", font_family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace")
css(".font-sans", font_family="ui-sans-serif,system-ui,sans-serif")

# Write
os.makedirs("app/static", exist_ok=True)
with open("app/static/tailwind.min.css", "w", encoding="utf-8") as f:
    f.write("\n".join(out))

size = os.path.getsize("app/static/tailwind.min.css")
print(f"Done: app/static/tailwind.min.css ({size:,} bytes)")
