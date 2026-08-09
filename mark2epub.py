import markdown
import os
from xml.dom import minidom
import zipfile
import sys
import json
import re
from xml.sax.saxutils import escape as xml_escape


def get_all_filenames(the_dir, extensions=[]):
    if not os.path.exists(the_dir):
        return []
    all_files = [x for x in os.listdir(the_dir)]
    all_files = [x for x in all_files if x.split(".")[-1].lower() in extensions]
    return all_files


def extract_title_from_md(filepath):
    """Extracts title from first heading in markdown file."""
    if not os.path.exists(filepath):
        base = os.path.basename(filepath).rsplit(".", 1)[0]
        return base.replace("_", " ").title()
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            m = re.match(r'^#{1,6}\s+(.+)$', line)
            if m:
                return re.sub(r'[*_`#]', '', m.group(1)).strip()
    base = os.path.basename(filepath).rsplit(".", 1)[0]
    return base.replace("_", " ").title()


def extract_toc_items_from_md(filepath):
    """
    Extracts heading level, title, and slug anchor from markdown file.
    Returns: [(level, title, slug), ...]
    """
    items = []
    if not os.path.exists(filepath):
        return items

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            m = re.match(r'^(#{1,3})\s+(.+)$', line)
            if m:
                level = len(m.group(1))
                raw_title = m.group(2).strip()
                clean_title = re.sub(r'[*_`#]', '', raw_title).strip()
                slug = clean_title.lower()
                slug = re.sub(r'[^\w\s-]', '', slug)
                slug = re.sub(r'[\s_]+', '-', slug).strip('-')
                items.append((level, clean_title, slug))
    return items


def parse_chapter_pages(pages_str):
    if not pages_str:
        return []
    parts = re.split(r'[,\s]+', str(pages_str).strip())
    pages = []
    for p in parts:
        if p.isdigit():
            val = int(p)
            if val > 0:
                pages.append(val)
    return sorted(list(set(pages)))


def extract_title_from_md_string(content):
    for line in content.splitlines():
        line = line.strip()
        m = re.match(r'^#{1,6}\s+(.+)$', line)
        if m:
            return re.sub(r'[*_`#]', '', m.group(1)).strip()
    return None


def split_markdown_into_chapters(work_dir, chapter_pages_str=None):
    """
    Splits single markdown file in work_dir into separate chapter files by headings.
    Returns: [{"markdown": "chapter_00.md", "title": "...", "css": ""}, ...]
    """
    md_files = [f for f in os.listdir(work_dir) if f.endswith(".md") and not f.startswith("chapter_") and not f.endswith(".bak")]
    if not md_files:
        md_files = [f for f in os.listdir(work_dir) if f.endswith(".md") and not f.endswith(".bak")]

    if not md_files:
        return []

    # If there are already multiple chapter files, use them
    if len(md_files) > 1 and any(f.startswith("chapter_") for f in md_files):
        chapters = []
        for md_file in sorted(md_files):
            title = extract_title_from_md(os.path.join(work_dir, md_file))
            chapters.append({"markdown": md_file, "title": title, "css": ""})
        return chapters

    main_md_filename = md_files[0]
    main_md_path = os.path.join(work_dir, main_md_filename)
    with open(main_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    h1_count = sum(1 for l in lines if re.match(r'^#\s+\S+', l))
    h2_count = sum(1 for l in lines if re.match(r'^##\s+\S+', l))

    if h1_count >= 1:
        split_pattern = r'^(?=#\s+\S+)'
    elif h2_count >= 1:
        split_pattern = r'^(?=##\s+\S+)'
    else:
        split_pattern = r'^(?=#{1,3}\s+\S+)'

    raw_sections = re.split(split_pattern, content, flags=re.MULTILINE)
    sections = [s.strip() for s in raw_sections if s.strip()]

    if len(sections) <= 1:
        title = extract_title_from_md(main_md_path)
        return [{"markdown": main_md_filename, "title": title, "css": ""}]

    chapters = []
    for idx, sec in enumerate(sections):
        first_line = sec.splitlines()[0] if sec.splitlines() else ""
        m = re.match(r'^#{1,6}\s+(.+)$', first_line)
        if m:
            title = re.sub(r'[*_`#]', '', m.group(1)).strip()
        else:
            title = "Front Matter" if idx == 0 else f"Chapter {idx}"

        chapter_filename = f"chapter_{idx:02d}.md"
        chapter_filepath = os.path.join(work_dir, chapter_filename)
        with open(chapter_filepath, "w", encoding="utf-8") as f:
            f.write(sec + "\n")

        chapters.append({"markdown": chapter_filename, "title": title, "css": ""})

    if main_md_filename != "chapter_00.md" and os.path.exists(main_md_path):
        os.rename(main_md_path, main_md_path + ".bak")

    return chapters


def get_packageOPF_XML(md_filenames=[], image_filenames=[], css_filenames=[], description_data=None):
    doc = minidom.Document()

    package = doc.createElement('package')
    package.setAttribute('xmlns', "http://www.idpf.org/2007/opf")
    package.setAttribute('version', "3.0")
    package.setAttribute('xml:lang', "en")
    package.setAttribute("unique-identifier", "pub-id")

    ## Metadata
    metadata = doc.createElement('metadata')
    metadata.setAttribute('xmlns:dc', 'http://purl.org/dc/elements/1.1/')

    for k, v in description_data.get("metadata", {}).items():
        if len(v):
            x = doc.createElement(k)
            for metadata_type, id_label in [("dc:title", "title"), ("dc:creator", "creator"), ("dc:identifier", "book-id")]:
                if k == metadata_type:
                    x.setAttribute('id', id_label)
            x.appendChild(doc.createTextNode(v))
            metadata.appendChild(x)

    ## Manifest
    manifest = doc.createElement('manifest')

    x = doc.createElement('item')
    x.setAttribute('id', "toc")
    x.setAttribute('properties', "nav")
    x.setAttribute('href', "TOC.xhtml")
    x.setAttribute('media-type', "application/xhtml+xml")
    manifest.appendChild(x)

    x = doc.createElement('item')
    x.setAttribute('id', "ncx")
    x.setAttribute('href', "toc.ncx")
    x.setAttribute('media-type', "application/x-dtbncx+xml")
    manifest.appendChild(x)

    x = doc.createElement('item')
    x.setAttribute('id', "titlepage")
    x.setAttribute('href', "titlepage.xhtml")
    x.setAttribute('media-type', "application/xhtml+xml")
    manifest.appendChild(x)

    for i, md_filename in enumerate(md_filenames):
        x = doc.createElement('item')
        x.setAttribute('id', f"s{i:05d}")
        x.setAttribute('href', f"s{i:05d}-{md_filename.split('.')[0]}.xhtml")
        x.setAttribute('media-type', "application/xhtml+xml")
        manifest.appendChild(x)

    cover_img = description_data.get("cover_image", "") if description_data else ""
    for i, image_filename in enumerate(image_filenames):
        x = doc.createElement('item')
        x.setAttribute('id', f"image-{i:05d}")
        x.setAttribute('href', f"images/{image_filename}")
        lower_name = image_filename.lower()
        if lower_name.endswith(".gif"):
            x.setAttribute('media-type', "image/gif")
        elif lower_name.endswith((".jpg", ".jpeg")):
            x.setAttribute('media-type', "image/jpeg")
        elif lower_name.endswith(".png"):
            x.setAttribute('media-type', "image/png")
        if cover_img and image_filename == cover_img:
            x.setAttribute('properties', "cover-image")

            y = doc.createElement('meta')
            y.setAttribute('name', "cover")
            y.setAttribute('content', f"image-{i:05d}")
            metadata.appendChild(y)
        manifest.appendChild(x)

    for i, css_filename in enumerate(css_filenames):
        x = doc.createElement('item')
        x.setAttribute('id', f"css-{i:05d}")
        x.setAttribute('href', f"css/{css_filename}")
        x.setAttribute('media-type', "text/css")
        manifest.appendChild(x)

    ## Spine
    spine = doc.createElement('spine')
    spine.setAttribute('toc', "ncx")

    x = doc.createElement('itemref')
    x.setAttribute('idref', "titlepage")
    x.setAttribute('linear', "yes")
    spine.appendChild(x)
    for i, md_filename in enumerate(md_filenames):
        x = doc.createElement('itemref')
        x.setAttribute('idref', f"s{i:05d}")
        x.setAttribute('linear', "yes")
        spine.appendChild(x)

    guide = doc.createElement('guide')
    x = doc.createElement('reference')
    x.setAttribute('type', "cover")
    x.setAttribute('title', "Cover image")
    x.setAttribute('href', "titlepage.xhtml")
    guide.appendChild(x)

    package.appendChild(metadata)
    package.appendChild(manifest)
    package.appendChild(spine)
    package.appendChild(guide)
    doc.appendChild(package)

    return doc.toprettyxml()


def get_container_XML():
    container_data = """<?xml version="1.0" encoding="UTF-8" ?>\n"""
    container_data += """<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n"""
    container_data += """<rootfiles>\n"""
    container_data += """<rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/>\n"""
    container_data += """</rootfiles>\n</container>"""
    return container_data


def get_coverpage_XML(cover_image_path):
    all_xhtml = """<?xml version="1.0" encoding="utf-8"?>\n"""
    all_xhtml += """<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">\n"""
    all_xhtml += """<head>\n</head>\n<body>\n"""
    if cover_image_path:
        all_xhtml += """<img src="images/{}" style="height:100%;max-width:100%;"/>\n""".format(cover_image_path)
    all_xhtml += """</body>\n</html>"""
    return all_xhtml


def get_TOC_XML(default_css_filenames, chapters_info, work_dir="."):
    ## Returns the XML data for the TOC.xhtml file
    toc_xhtml = """<?xml version="1.0" encoding="UTF-8"?>\n"""
    toc_xhtml += """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">\n"""
    toc_xhtml += """<head>\n<meta http-equiv="default-style" content="text/html; charset=utf-8"/>\n"""
    toc_xhtml += """<title>Contents</title>\n"""

    for css_filename in default_css_filenames:
        toc_xhtml += """<link rel="stylesheet" href="css/{}" type="text/css"/>\n""".format(css_filename)

    toc_xhtml += """</head>\n<body>\n"""
    toc_xhtml += """<nav epub:type="toc" role="doc-toc" id="toc">\n<h2>Contents</h2>\n<ol epub:type="list">\n"""

    for i, chapter in enumerate(chapters_info):
        md_filename = chapter["markdown"]
        chapter_title = chapter.get("title") or extract_title_from_md(os.path.join(work_dir, md_filename))
        xhtml_filename = f"s{i:05d}-{md_filename.split('.')[0]}.xhtml"
        toc_xhtml += f"""  <li><a href="{xhtml_filename}">{xml_escape(chapter_title)}</a></li>\n"""

    toc_xhtml += """</ol>\n</nav>\n</body>\n</html>"""
    return toc_xhtml


def get_TOCNCX_XML(chapters_info, work_dir=".", book_title="Document"):
    ## Returns the XML data for the TOC.ncx file
    toc_ncx = """<?xml version="1.0" encoding="UTF-8"?>\n"""
    toc_ncx += """<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" xml:lang="en" version="2005-1">\n"""
    toc_ncx += """<head>\n"""
    toc_ncx += """  <meta name="dtb:uid" content="document-1"/>\n"""
    toc_ncx += """  <meta name="dtb:depth" content="1"/>\n"""
    toc_ncx += """  <meta name="dtb:totalPageCount" content="0"/>\n"""
    toc_ncx += """  <meta name="dtb:maxPageNumber" content="0"/>\n"""
    toc_ncx += """</head>\n"""
    toc_ncx += f"""<docTitle><text>{xml_escape(book_title)}</text></docTitle>\n"""
    toc_ncx += """<navMap>\n"""

    play_order = 1
    for i, chapter in enumerate(chapters_info):
        md_filename = chapter["markdown"]
        chapter_title = chapter.get("title") or extract_title_from_md(os.path.join(work_dir, md_filename))
        xhtml_filename = f"s{i:05d}-{md_filename.split('.')[0]}.xhtml"

        toc_ncx += f"""  <navPoint id="navpoint-{i}" playOrder="{play_order}">\n"""
        play_order += 1
        toc_ncx += f"""    <navLabel><text>{xml_escape(chapter_title)}</text></navLabel>\n"""
        toc_ncx += f"""    <content src="{xhtml_filename}"/>\n"""
        toc_ncx += """  </navPoint>\n"""

    toc_ncx += """</navMap>\n</ncx>"""
    return toc_ncx


def get_chapter_XML(md_filename, css_filenames, work_dir="."):
    with open(os.path.join(work_dir, md_filename), "r", encoding="utf-8") as f:
        markdown_data = f.read()

    html_text = markdown.markdown(markdown_data,
                                  extensions=["codehilite", "tables", "fenced_code", "footnotes", "toc"],
                                  extension_configs={"codehilite": {"guess_lang": False}}
                                  )

    all_xhtml = """<?xml version="1.0" encoding="UTF-8"?>\n"""
    all_xhtml += """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">\n"""
    all_xhtml += """<head>\n<meta http-equiv="default-style" content="text/html; charset=utf-8"/>\n"""

    for css_filename in css_filenames:
        all_xhtml += """<link rel="stylesheet" href="css/{}" type="text/css"/>\n""".format(css_filename)

    all_xhtml += """</head>\n<body>\n"""
    all_xhtml += html_text
    all_xhtml += """\n</body>\n</html>"""

    return all_xhtml


if __name__ == "__main__":
    if len(sys.argv[1:]) < 2:
        print("\nUsage:\n    python md2epub.py <markdown_directory> <output_file.epub>")
        exit(1)

    work_dir = sys.argv[1]
    output_path = sys.argv[2]

    images_dir = os.path.join(work_dir, r'images/')
    css_dir = os.path.join(work_dir, r'css/')

    desc_path = os.path.join(work_dir, "description.json")
    if os.path.exists(desc_path):
        with open(desc_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
    else:
        json_data = {}

    chapters_info = json_data.get("chapters", [])
    chapter_pages_val = json_data.get("chapter_pages") or os.getenv("CHAPTER_PAGES", "")
    if not chapters_info or len(chapters_info) <= 1:
        split_chapters = split_markdown_into_chapters(work_dir, chapter_pages_str=chapter_pages_val)
        if split_chapters:
            chapters_info = split_chapters
            json_data["chapters"] = chapters_info

    # Save/update description.json
    with open(desc_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4)

    all_md_filenames = [ch["markdown"] for ch in chapters_info]
    all_css_filenames = json_data.get("default_css", [])[:]
    for chapter in chapters_info:
        if chapter.get("css") and (not chapter["css"] in all_css_filenames):
            all_css_filenames.append(chapter["css"])

    all_image_filenames = get_all_filenames(images_dir, extensions=["gif", "jpg", "jpeg", "png"])

    book_title = json_data.get("metadata", {}).get("dc:title", "Document")

    with zipfile.ZipFile(output_path, "w") as myZipFile:
        myZipFile.writestr("mimetype", "application/epub+zip", zipfile.ZIP_DEFLATED)

        container_data = get_container_XML()
        myZipFile.writestr("META-INF/container.xml", container_data, zipfile.ZIP_DEFLATED)

        package_data = get_packageOPF_XML(md_filenames=all_md_filenames,
                                          image_filenames=all_image_filenames,
                                          css_filenames=all_css_filenames,
                                          description_data=json_data
                                          )
        myZipFile.writestr("OPS/package.opf", package_data, zipfile.ZIP_DEFLATED)

        coverpage_data = get_coverpage_XML(json_data.get("cover_image", ""))
        myZipFile.writestr("OPS/titlepage.xhtml", coverpage_data.encode('utf-8'), zipfile.ZIP_DEFLATED)

        for i, chapter in enumerate(chapters_info):
            chapter_md_filename = chapter["markdown"]
            chapter_css_filenames = json_data.get("default_css", [])[:]
            if chapter.get("css"):
                chapter_css_filenames.append(chapter["css"])

            chapter_data = get_chapter_XML(chapter_md_filename, chapter_css_filenames, work_dir=work_dir)
            myZipFile.writestr(f"OPS/s{i:05d}-{chapter_md_filename.split('.')[0]}.xhtml",
                               chapter_data.encode('utf-8'),
                               zipfile.ZIP_DEFLATED)

        toc_xml_data = get_TOC_XML(json_data.get("default_css", []), chapters_info, work_dir=work_dir)
        myZipFile.writestr("OPS/TOC.xhtml", toc_xml_data.encode('utf-8'), zipfile.ZIP_DEFLATED)

        toc_ncx_data = get_TOCNCX_XML(chapters_info, work_dir=work_dir, book_title=book_title)
        myZipFile.writestr("OPS/toc.ncx", toc_ncx_data.encode('utf-8'), zipfile.ZIP_DEFLATED)

        for i, image_filename in enumerate(all_image_filenames):
            with open(os.path.join(images_dir, image_filename), "rb") as f:
                filedata = f.read()
            myZipFile.writestr(f"OPS/images/{image_filename}",
                               filedata,
                               zipfile.ZIP_DEFLATED)

        for i, css_filename in enumerate(all_css_filenames):
            with open(os.path.join(css_dir, css_filename), "rb") as f:
                filedata = f.read()
            myZipFile.writestr(f"OPS/css/{css_filename}",
                               filedata,
                               zipfile.ZIP_DEFLATED)

    print("eBook creation complete")
