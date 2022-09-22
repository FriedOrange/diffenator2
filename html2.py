"""
"""
from dataclasses import dataclass, field
from jinja2 import Environment, FileSystemLoader
from fontTools.ttLib import TTFont
import os
import shutil
from diffenator.shape import Renderable


WIDTH_CLASS_TO_CSS = {
    1: "50",
    2: "62.5",
    3: "75",
    4: "87.5",
    5: "100",
    6: "112.5",
    7: "125",
    8: "150",
    9: "200",
}


@dataclass
class CSSFontFace(Renderable):
    ttfont: TTFont
    suffix: str = ""
    filename: str = field(init=False)
    familyname: str = field(init=False)
    classname: str = field(init=False)

    def __post_init__(self):
        self.filename = os.path.basename(self.ttfont.reader.file.name)
        self.cssfamilyname = _family_name(self.ttfont, self.suffix)
        self.stylename = self.ttfont["name"].getBestSubFamilyName()
        self.classname = self.cssfamilyname.replace(" ", "-")
        self.font_style = "normal" if "Italic" not in self.stylename else "italic"
        
        if "fvar" in self.ttfont:
            fvar = self.ttfont["fvar"]
            axes = {a.axisTag: a for a in fvar.axes}
            if "wght" in axes:
                min_weight = int(axes["wght"].minValue)
                max_weight = int(axes["wght"].maxValue)
                self.font_weight = f"{min_weight} {max_weight}"
            if "wdth" in axes:
                min_width = int(axes["wdth"].minValue)
                max_width = int(axes["wdth"].maxValue)
                self.font_stretch = f"{min_width}% {max_width}%"
            if "ital" in axes:
                pass
            if "slnt" in axes:
                min_angle = int(axes["slnt"].minValue)
                max_angle = int(axes["slnt"].maxValue)
                self.font_style = f"oblique {min_angle}deg {max_angle}deg"


def _family_name(ttFont, suffix=""):
    familyname = ttFont["name"].getBestFamilyName()
    if suffix:
        return f"{suffix} {familyname}"
    else:
        return familyname


@dataclass
class CSSFontStyle(Renderable):
    familyname: str
    stylename: str
    coords: dict
    suffix: str = ""
    
    def __post_init__(self):
        self.cssfamilyname = f"{self.suffix} {self.familyname}"
        self.full_name = f"{self.familyname} {self.stylename}"
        self.class_name = f"{self.suffix} {self.familyname} {self.stylename}".replace(" ", "-")


def get_font_styles(ttfonts, suffix=""):
    res = []
    for ttfont in ttfonts:
        family_name = ttfont["name"].getBestFamilyName()
        if "fvar" in ttfont:
            fvar = ttfont["fvar"]
            for inst in fvar.instances:
                name_id = inst.subfamilyNameID
                style_name = ttfont["name"].getName(name_id, 3, 1, 0x409).toUnicode()
                coords = inst.coordinates
                res.append(CSSFontStyle(family_name, style_name, coords, suffix))
        else:
            style_name = ttfont["name"].getBestSubFamilyName()
            res.append(CSSFontStyle(family_name, style_name, {
                "wght": ttfont["OS/2"].usWeightClass,
                "wdth": WIDTH_CLASS_TO_CSS[ttfont["OS/2"].usWidthClass],
                }
            ),
            suffix)
    return res


def proof_rendering(ttFonts, template, dst="out"):
    font_faces = [CSSFontFace(f) for f in ttFonts]
    font_styles = get_font_styles(ttFonts)
    _package(template, dst, font_faces=font_faces, font_styles=font_styles)


def diff_rendering(ttFonts_old, ttFonts_new, template, dst="out"):
    font_faces_old = [CSSFontFace(f, "old") for f in ttFonts_old]
    font_styles_old = get_font_styles(ttFonts_old, "old")

    font_faces_new = [CSSFontFace(f, "new") for f in ttFonts_new]
    font_styles_new = get_font_styles(ttFonts_new, "new")

    font_styles_old, font_styles_new = _match_styles(font_styles_old, font_styles_new)
    _package(
        template,
        dst,
        font_faces_old=font_faces_old,
        font_styles_old=font_styles_old,
        font_faces_new=font_faces_new,
        font_styles_new=font_styles_new,
    )


def _package(template_fp, dst, **kwargs):
    if not os.path.exists(dst):
        os.mkdir(dst)

    # write doc
    env = Environment(
        loader=FileSystemLoader(os.path.dirname(template_fp)),
    )
    template = env.get_template(os.path.basename(template_fp))
    doc = template.render(**kwargs)
    dst_doc = os.path.join(dst, os.path.basename(template_fp))
    with open(dst_doc, "w") as out_file:
        out_file.write(doc)

    # copy fonts
    for k in ("font_faces", "font_faces_old", "font_faces_new"):
        if k in kwargs:
            for font in kwargs[k]:
                out_fp = os.path.join(dst, font.filename)
                shutil.copy(font.ttfont.reader.file.name, out_fp)


def _match_styles(styles_old: list[CSSFontStyle], styles_new: list[CSSFontStyle]):
    old = {s.full_name: s for s in styles_old}
    new = {s.full_name: s for s in styles_new}
    shared = set(old) & set(new)
    if not shared:
        raise ValueError("No matching fonts found")
    return [s for s in styles_old if s.full_name in shared], [s for s in styles_new if s.full_name in shared]


if __name__ == "__main__":
    import os

    fonts = [
        TTFont(os.environ["mavenvf"]),
        TTFont("/Users/marcfoley/Type/fonts/ofl/inconsolata/Inconsolata[wdth,wght].ttf"),
    ]
    fonts2 = fonts[:]
    fonts2.pop()
    diff_rendering(fonts, fonts2, template="templates/waterfall.html", dst="out")