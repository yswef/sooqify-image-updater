# =========================================================
# Sooqify Image Updater
# Scans the root folder, reads each product folder and its product_info.txt, and
# orders images so 1.png is always the main image.
# =========================================================
# Developer: Yousef Alhamzy

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
INFO_FILENAME = "product_info.txt"

# Matches product_info.txt lines: "Style Code: XXXX", and also "Product ID: 123" if
# that gets reintroduced by the source app later (forward-compatible, no change needed
# here - see the note at the bottom of this file about the product_id field).
INFO_LINE_PATTERN = re.compile(r"^\s*([A-Za-z ]+)\s*:\s*(.*)$")


@dataclass
class ProductFolder:
    path: str
    folder_name: str
    style_code: str = ""
    product_id: str = ""          # Display-only - see the note at the bottom of this file; not used for the safe verification check.
    name_en: str = ""
    name_ar: str = ""
    added_by: str = ""
    date_added: str = ""
    images: list[str] = field(default_factory=list)   # Ordered: [main, secondary...]
    info_found: bool = False

    @property
    def has_search_key(self) -> bool:
        """Any search key we can use on the Sooqify dashboard - the style code or the name."""
        return bool(self.style_code or self.name_en)


def parse_product_info(info_path: str) -> dict[str, str]:
    """Reads product_info.txt and returns its values as a simple dict, independent of line order."""
    values: dict[str, str] = {}
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            for line in f:
                match = INFO_LINE_PATTERN.match(line)
                if not match:
                    continue
                key = match.group(1).strip().lower()
                value = match.group(2).strip()
                if value == "-":
                    value = ""
                values[key] = value
    except OSError:
        pass
    return values


def sort_images(image_filenames: list[str]) -> list[str]:
    """
    Orders images so "1.xxx" always comes first (the main image), then the rest
    numerically. Any non-numeric name is pushed to the end instead of breaking the order.
    """
    def sort_key(filename: str) -> tuple[int, int | str]:
        stem = os.path.splitext(filename)[0]
        return (0, int(stem)) if stem.isdigit() else (1, filename.lower())

    return sorted(image_filenames, key=sort_key)


def scan_product_folder(folder_path: str) -> ProductFolder | None:
    """Builds a ProductFolder from a single product folder, or None if it has no images (or couldn't be read)."""
    folder_name = os.path.basename(folder_path.rstrip(os.sep))
    try:
        entries = os.listdir(folder_path)
    except OSError:
        # Permissions locked or an invalid path for this specific folder - skip just this one instead of failing the whole scan.
        return None

    image_files = [
        name for name in entries
        if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
    ]
    if not image_files:
        return None

    product = ProductFolder(
        path=folder_path,
        folder_name=folder_name,
        images=sort_images(image_files),
    )

    info_path = os.path.join(folder_path, INFO_FILENAME)
    if os.path.isfile(info_path):
        values = parse_product_info(info_path)
        product.info_found = True
        product.style_code = values.get("style code", "")
        product.product_id = values.get("product id", "")
        product.added_by = values.get("added by", "")
        product.date_added = values.get("date added", "")
        try:
            # The first two "Name:" lines are English then Arabic, in the same order as the original file.
            with open(info_path, "r", encoding="utf-8") as f:
                name_lines = [
                    match.group(2).strip()
                    for line in f
                    if (match := INFO_LINE_PATTERN.match(line)) and match.group(1).strip().lower() == "name"
                ]
            if name_lines:
                product.name_en = name_lines[0]
            if len(name_lines) > 1:
                product.name_ar = name_lines[1]
        except OSError:
            pass  # Same protection as above - don't fail the whole scan for one product's file.

    return product


def scan_root_folder(root_folder: str) -> list[ProductFolder]:
    """
    Scans the root folder (any organization depth - brand/date/product), returning
    every folder that contains images as one ProductFolder.

    Once a folder is recognized as a product (it has images), we do not keep descending
    into its subfolders - if a product has an extra subfolder (a backup copy, say),
    this prevents it from also being treated as a separate product (duplicate/polluted results).
    """
    products: list[ProductFolder] = []
    for current_dir, sub_dirs, _files in os.walk(root_folder):
        product = scan_product_folder(current_dir)
        if product:
            products.append(product)
            sub_dirs[:] = []  # Don't descend into subfolders of a folder already identified as a product.
    return products


# =========================================================
# Note: the "Product ID" column may be missing from older versions of
# product_info.txt. This does not affect the safety of the product-identity
# verification before editing: the actual check (uploader.search_and_open_product)
# relies entirely on the real ID returned by the central sync system
# (sync_client.lookup_product_by_style_code), compared against the "Tags" column shown
# on the Sooqify dashboard itself - not on this local field at all. product_id here is
# display-only (shown in the UI if present), and its absence never disables any safety step.
# =========================================================
