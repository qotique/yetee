import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

tree = ET.parse("../db/types.xml")
root = tree.getroot()


@dataclass
class Type:
    name: str
    nominal: int
    lifetime: int
    restock: int
    min: int
    quantmin: int
    quantmax: int
    cost: int
    flags: Any
    category: Any
    usage: Any


for type_ in root.iter("type"):
    print(type_.attrib["name"])
    # print(type_.find("name").text)
    print("nominal", type_.find("nominal").text)
    print("lifetime", type_.find("lifetime").text)
    print("restock", type_.find("restock").text)
    print("min", type_.find("min").text)
    print("quantmin", type_.find("quantmin").text)
    print("quantmax", type_.find("quantmax").text)
    print("cost", type_.find("cost").text)
    print("flags", type_.find("flags").attrib)
    print("category", type_.find("category").attrib if type_.find("category") is not None else None)
    print("usage", type_.find("usage").attrib if type_.find("usage") is not None else None)