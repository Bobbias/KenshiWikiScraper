import argparse
import requests
from bs4 import BeautifulSoup
from pygments import highlight
from pygments.lexers import HtmlLexer
from pygments.formatters import Terminal256Formatter
from pprint import pprint, PrettyPrinter
from os import mkdir
from os.path import exists, dirname, join, relpath
from requests import HTTPError
from returns.result import ResultE, Success, Failure
from colorlog import ColoredFormatter
import logging
import apsw
import re
import itertools
from sys import argv, stdout, exc_info
import traceback

html_parser = "html.parser"

to_strip = r'c\.|[\n\t]|^ +| +$'

data_parser = '|'.join([r'-(?P<NAME>[A-Za-z ]+)',
                        r'(?P<INTEGER>[+-]?[\d,]+)$',
                        r'(?P<FLOAT>\d+.\d+)$',
                        r'(?P<MULTIPLIER>[+-]?[\d.]+x)',
                        r'(?P<PERCENTAGE>[+-]?[\d.]+%)',
                        r'(?P<WEIGHT>\d+)(?= kg)'])


def setup_logging(debug, verbose):
    log_folder = join(dirname(__file__), 'logs')
    filename = join(log_folder, 'KenshiWikiScraper.log')
    if not exists(log_folder):
        mkdir(log_folder)
    # define a handler which logs DEBUG or higher to a file
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(name)-12s [%(levelname)-8s] %(message)s',
                        datefmt='%m-%d %H:%M',
                        filename=filename,
                        filemode='w')
    # define a Handler which writes messages to stdout. The level of verbosity is controlled by the debug and verbose
    # command line arguments
    console = logging.StreamHandler(stdout)
    level = logging.ERROR
    if debug:
        level = logging.INFO
    elif verbose:
        level = logging.DEBUG
    console.setLevel(level)
    # set a format which is simpler for console use, with color output
    formatter = ColoredFormatter('%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s',
                                 reset=True,
                                 log_colors={
                                         'DEBUG':    'cyan',
                                         'INFO':     'green',
                                         'WARNING':  'yellow',
                                         'ERROR':    'red',
                                         'CRITICAL': 'red,bg_white',
                                         },
                                 style='%')
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger('KenshiWikiScraper').addHandler(console)


class ImageExistsError(RuntimeError):
    """
    Extends `RuntimeError`.
    This exception indicates that the image file contained in the `filename` attribute already exists on disk.
    Used to pass information back through a returns.result.ResultE instance.
    """

    def __init__(self, filename: str):
        """
        Extend `RuntimeError`.

        :param filename: the file which caused this exception to be thrown.
        :type filename: str
        """
        self.filename = filename


def esc_color(val):
    # ensure we're in the proper range
    val = val % 16777216
    # extract the rgb values
    r, g, b = (val / (256 ** 3)) % 255, (val / (256 ** 2)) % 255, val % 255
    return f"\x1B[38;2;{r};{g};{b}m"


def esc_reset():
    return f"\x1B[0m"


def print_exc_plus(frames_to_print=None, item_limit=10):
    """
    Print the usual traceback information, followed by a listing of all the
    local variables in each frame.

    :param frames_to_print: the number of frames starting at the current frame, to display, set to None to disable limit
    :type frames_to_print: Union[int, NoneType]
    :param item_limit: the number of local variables to display, set to None to disable limit
    :type item_limit: Union[int, NoneType]
    """
    pp = PrettyPrinter(indent=4, width=45, depth=1, compact=False)

    tb = exc_info()[2]
    while 1:
        if not tb.tb_next:
            break
        tb = tb.tb_next
    stack = []
    f = tb.tb_frame
    while f:
        stack.append(f)
        f = f.f_back
    # stack is initially latest to earliest, so grab first x frames before reversing for display
    if frames_to_print:
        stack = stack[:frames_to_print]
    stack.reverse()
    print(esc_color(0xFF0000), end='')
    traceback.print_exc(chain=True)
    print(esc_reset(), end='')
    print("Locals by frame, innermost last")
    for frame in stack:
        print()
        print("Frame %s in %s at line %s" % (frame.f_code.co_name,
                                             frame.f_code.co_filename,
                                             frame.f_lineno))
        for i, (key, value) in enumerate(frame.f_locals.items()):
            if i > item_limit:
                break
            print("\t%20s = " % key, )
            # We have to be careful not to cause a new error in our error
            # printer! Calling str() on an unknown object could cause an
            # error we don't want.
            try:
                if type(value) is dict and len(value.keys()) > item_limit:
                    output = {k: v for k, v in value.items()[:item_limit]}
                    pp.pprint(output)
                elif type(value) in [list, set] and len(value) > item_limit:
                    output = type(value)(item for item in value[:item_limit])
                    pp.pprint(output)
                else:
                    pp.pprint(value)
            except:
                print(f"{esc_color(0xFF0000)}<ERROR WHILE PRINTING VALUE>{esc_reset()}")


def process_page(url, debug):
    log = logging.getLogger('KenshiWikiScraper')
    # this dictionary holds the final results after processing the entire page.
    data = []
    log.info(f"Name: {url.split('/')[-1]}")

    with requests.get(url) as page:
        soup = BeautifulSoup(page.content, html_parser)

        # identify the beginning of the Homemade variants.
        homemade_start = soup.find(id="Homemade")
        if homemade_start:
            # find all variants preceding the homemade section
            found_variants = homemade_start.findAllPrevious(
                    style="border: solid #553019 2px; margin: 0 0 0 0; line-height:1; font-size: 80%; background: #3e3834;"
                          " color:#C0C0C0; width: 250px; padding: 0.3em; text-align: left; float:none; clear:none;"
                          " display:inline-table;")
            weapon_class = found_variants[0].find_all_next('td')[2].getText().strip().strip('[').rstrip(']')
            for variant in process_weapon_variants(debug, found_variants):
                variant['class'] = weapon_class
                variant['homemade'] = False
                data.append(variant)
            homemade_variants = homemade_start.findAllNext(
                    style="border: solid #553019 2px; margin: 0 0 0 0; line-height:1; font-size: 80%; background: #3e3834;"
                          " color:#C0C0C0; width: 250px; padding: 0.3em; text-align: left; float:none; clear:none;"
                          " display:inline-table;")
            for variant in process_weapon_variants(debug, homemade_variants):
                variant['class'] = weapon_class
                variant['homemade'] = True
                data.append(variant)
        # several weapons lack homemade variants entirely, so we need a different solution for those pages
        else:
            found_variants = soup.select("div.mw-parser-output>table:not(.navbox)")
            weapon_class = found_variants[0].find_all_next('td')[2].getText().strip().strip('[').rstrip(']')
            for variant in process_weapon_variants(debug, found_variants):
                variant['class'] = weapon_class
                variant['homemade'] = False
                data.append(variant)

    return data


def process_weapon_variants(debug, found_variants):
    log = logging.getLogger('KenshiWikiScraper')
    for i, result in enumerate(found_variants):
        variant_data = {}
        log.debug(f"Result {i}:")

        # begin searching through the contents of each result
        new_soup = BeautifulSoup(result.decode_contents(), html_parser)

        # Find the first image link in the result
        image = new_soup.find('a', class_="image")

        # print the link to the image
        log.debug(f"Image: {image['href']}")

        # download the image and save it to a file, only if the local file doesn't already exist
        variant_data['image_url'] = image['href']
        filename = image['href'].split('/')[-3]
        local_img = save_image(filename, image)
        variant_data['local_image'] = handle_image_result(local_img)

        # find the quality level of this variant
        variant_data['quality'] = new_soup.find("span").text.split('#')[1].strip(']').lstrip()

        # find all stat lines for the variant
        for stat_name, value in process_stat_lines(result):
            variant_data[stat_name] = value

        # print the full html of the result for debug purposes.
        # Prettify it, and then syntax highlight it with pygments before printing.
        if debug:
            pprint(variant_data.items())
            print("Full html:")
            pretty_result = result.prettify()
            highlighted = highlight(pretty_result, HtmlLexer(), Terminal256Formatter())
            print(highlighted)

        yield variant_data


def process_stat_lines(result):
    log = logging.getLogger('KenshiWikiScraper')
    new_soup = BeautifulSoup(result.decode_contents(), html_parser)
    item_stat = new_soup.findAll("tr")
    name = None
    # iterate over the inner data of each table representing an item variant, skipping the first few sections
    # (image, item name, and weapon class)
    for i, stat_result in enumerate(item_stat[3:]):
        log.debug(f'v: {stat_result}')
        # each stat is contained in a pair of `td` elements, the first one is the stat name, the second one
        # is the actual value
        for c in stat_result.findAll("td"):
            stripped = re.sub(to_strip, "", c.text)
            if name:
                oldname = name.lower().replace(" ", "_")
            for match in re.finditer(data_parser, stripped):
                if name := match.group("NAME"):
                    log.info(f'name: {name}')
                elif float_num := match.group("FLOAT"):
                    log.info(f'name: {oldname}, float: {float_num}')
                    yield oldname, float(float_num)
                elif integer := match.group("INTEGER"):
                    val = int(integer.replace(',', ''))
                    log.info(f'name: {oldname}, int: {val}')
                    yield oldname, val
                elif multiplier := match.group("MULTIPLIER"):
                    val = float(multiplier.rstrip("x"))
                    log.info(f'name: {oldname}, multiplier: {val}')
                    yield oldname, val
                elif percentage := match.group("PERCENTAGE"):
                    val = float(percentage.rstrip("%")) * 0.01
                    log.info(f'name: {oldname}, percentage: {val}')
                    yield oldname, val
                elif weight := match.group("WEIGHT"):
                    val = int(weight)
                    log.info(f'name: {oldname}, weight: {val}')
                    yield oldname, val


def handle_image_result(local_img):
    match local_img:
        case Success(value):
            return value
        case Failure(ImageExistsError):
            return ImageExistsError.filename
        case Failure(_):
            return "none"


def save_image(filename, image) -> ResultE[str]:
    log = logging.getLogger('KenshiWikiScraper')
    log.debug(f'dirname(__file__): {dirname(__file__)}')

    current_path = dirname(__file__)
    destination_directory = join(current_path, "images")
    destination_file = join(destination_directory, filename)

    log.debug(f'destination_directory: {destination_directory}')
    log.debug(f'Writing image file file to {destination_file}')

    # if the file doesn't exist, try to download it
    if not exists(destination_file):
        # create directory if it's missing
        if not exists(destination_directory):
            mkdir(destination_directory)
        # if the image was downloaded, save it to a local file and return a success code
        # todo: handle write failure after download
        with requests.get(image['href']) as img:
            if img.status_code == 200 and len(img.content) != 0:
                with open(destination_file, 'wb') as img_file:
                    img_file.write(img.content)
                    log.info(f'SUCCESS: {image["href"]} downloaded successfully.')
                    return Success(destination_file)
            # if download failed for some reason, return a Failure containing the error
            else:
                try:
                    img.raise_for_status()
                except HTTPError as http_err:
                    msg = f'FAILURE: Failed to download image {image["href"]}, reason: {http_err}.'
                    log.error(msg)
                    return Failure(HTTPError(msg))
    # if the file already exists locally, return a failure indicating we did not download the image.
    # note: this could probably be refactored. we should check for existing files before calling this
    #       function
    else:
        log.info(f'Download of {image["href"]} aborted. {destination_file} already exists.')
        return Failure(ImageExistsError(destination_file))


def handle_args(args):
    parser = argparse.ArgumentParser(description="Scrapes https://kenshi.fandom.com for weapon data and creates a"
                                                 " sqlite3 database to be consumed by KenshiCalculator.")
    # if `--debug` is present, but no value follows, it produces `on`, otherwise it defaults to off
    parser.add_argument("-d", "--debug", nargs="?", const="on", default="off",
                        choices=["off", "on", "true", "false", "verbose"])
    parser.add_argument("output", nargs="?")
    return parser.parse_args(args)


def get_weapon_pages():
    website = "https://kenshi.fandom.com"
    weapons_url = website + "/wiki/Weapons"
    pages = []
    with requests.get(weapons_url) as page:
        soup = BeautifulSoup(page.content, html_parser)
        results = soup.select("table.navbox:nth-of-type(3)>tbody>tr>td>table>tbody>tr>td.navbox-list>div>a")
        heavy_weapons = soup.select(
                "table.navbox:nth-of-type(3)>tbody>tr>td>table>tbody>tr>td.navbox-list>table>tbody>tr>td>div>a")
        for result in results[:-14]:
            pages.append(website + result['href'])
        for result in heavy_weapons:
            pages.append(website + result['href'])
    return pages


def collect_possible_data_keys(data):
    possible_keys = set()
    for weapon in data.values():
        possible_keys.update(weapon[0].keys())
    return possible_keys


def collect_possible_weapon_classes(data):
    possible_classes = set()
    for weapon in data.values():
        possible_classes.add(weapon[0]['class'])
    return possible_classes


def collect_possible_weapon_quality_keys(data):
    possible_qualities = set()
    for weapon in data.values():
        for variant in weapon:
            possible_qualities.add(variant['quality'])
    return possible_qualities


def collect_possible_weapon_image_keys(data):
    images = set()
    for weapon in data.values():
        for variant in weapon:
            images.add(variant['local_image'])
    return images


def user_version(db):
    return db.cursor().execute("pragma user_version").fetchall()[0][0]


def make_table_schema(name, keys=None, foreign_keys=None, unique_colname=None):
    sql = f'CREATE TABLE IF NOT EXISTS "{name}" (\n'
    sql += make_id()
    if keys:
        for key, type_ in keys:
            key_is_unique = True if key == unique_colname else False
            sql += make_column(key, type_, key_is_unique)
    if foreign_keys:
        for key, table in foreign_keys:
            sql += make_foreign_key(key, table)
    sql += 'PRIMARY KEY("id" AUTOINCREMENT)\n);'
    return sql


def make_foreign_key(name, table):
    return f'FOREIGN KEY("{name}") REFERENCES "{table}"("id"),\n'


def make_id():
    return '"id" INTEGER NOT NULL UNIQUE,\n'


def make_column(name, type_, unique=False):
    return f'"{name}" {type_}{" UNIQUE" if unique else ""},\n'


# note: any foreign key must also be in columns
weapon_columns = [
        ('name', 'INTEGER'),
        ('image', 'INTEGER'),
        ('class', 'INTEGER'),
        ('quality', 'INTEGER'),
        ('armour_penetration', 'REAL'),
        ('attack_bonus', 'INTEGER'),
        ('blood_loss', 'REAL'),
        ('blunt_damage', 'REAL'),
        ('cutting_damage', 'REAL'),
        ('damage_vs_animals', 'REAL'),
        ('damage_vs_beak_thing', 'REAL'),
        ('damage_vs_bonedog', 'REAL'),
        ('damage_vs_gorillo', 'REAL'),
        ('damage_vs_humans', 'REAL'),
        ('damage_vs_leviathan', 'REAL'),
        ('damage_vs_robots', 'REAL'),
        ('damage_vs_skimmer', 'REAL'),
        ('damage_vs_small_spider', 'REAL'),
        ('damage_vs_spider', 'REAL'),
        ('defence_bonus', 'INTEGER'),
        ('homemade', 'INTEGER'),
        ('image_url', 'TEXT'),
        ('indoors_bonus', 'INTEGER'),
        ('required_strength_level', 'INTEGER'),
        ('sell_value', 'INTEGER'),
        ('value', 'INTEGER'),
        ('weight', 'INTEGER')]

weapon_foreign_keys = [
        ('name', 'WeaponName'),
        ('image', 'WeaponImage'),
        ('class', 'WeaponClass'),
        ('quality', 'WeaponQuality'),
        ]

weapon_class_keys = [('name', 'TEXT')]

weapon_name_keys = [('name', 'TEXT')]

weapon_quality_keys = [('name', 'TEXT')]

weapon_image_keys = [
        ('path', 'TEXT'),
        ('data', 'BLOB'),
        ]


def insert_weapon_images(paths):
    sql = 'INSERT INTO "WeaponImage" (path, data) VALUES\n'
    # note: currently cannot find a way to load binary data, just use the path for now.
    sql += ',\n'.join([f'("{relpath(path)}", "{relpath(path)}")' for path in paths])
    print(f'image query: {sql}')
    return sql


def insert_weapon_names(names):
    sql = 'INSERT INTO "WeaponName" (name) VALUES\n'
    sql += ',\n'.join([f'("{name}")' for name in names])
    return sql


def insert_weapon_qualities(qualities):
    sql = 'INSERT INTO "WeaponQuality" (name) VALUES\n'
    sql += ',\n'.join([f'("{quality}")' for quality in qualities])
    return sql


def insert_weapon_classes(classes):
    sql = 'INSERT INTO "WeaponClass" (name) VALUES\n'
    sql += ',\n'.join([f'("{class_}")' for class_ in classes])
    return sql


def insert_weapons(db, all_weapons):
    for name, variants in all_weapons.items():
        name = name.replace('%27', "'")
        print('=' * 10)
        print(f'Inserting weapon {name}')
        print('=' * 10)
        weapon_name_id_row = db.execute('Select id from "WeaponName" where name = ?', (name,)).fetchone()
        print(f'weapon_name_id_row: {weapon_name_id_row}')
        assert len(weapon_name_id_row) > 0, f"weapon_name_id_row length is 0, expected nonzero length"
        weapon_name_id = weapon_name_id_row[0]
        print(f'weapon_name_id: {weapon_name_id}')
        assert not weapon_name_id is None, "weapon_name_id is none, expected an integer"
        print('=' * 10)
        print(f'Processing {name} variants')
        print('=' * 10)
        for variant in variants:
            insert_weapon_variant(db, weapon_name_id, variant)


def convertToBinaryData(filename):
    # Convert digital data to binary format
    with open(filename, 'rb') as file:
        blobData = file.read()
    return blobData


def insert_weapon_variant(db, weapon_name_id, variant):
    print('=' * 10)
    print(f'name id: {weapon_name_id}')
    print('=' * 10)
    weapon_class_id = db.execute('SELECT id FROM "WeaponClass" WHERE name = ?', (variant['class'],)).fetchone()[0]
    print(f'{variant["class"]}: id {weapon_class_id}')
    print('=' * 10)
    weapon_quality_id = db.execute('SELECT id FROM "WeaponQuality" WHERE name = ?', (variant['quality'],)).fetchone()[0]
    print(f'{variant["quality"]}: id {weapon_quality_id}')
    print('=' * 10)

    weapon_image_id = db.execute('SELECT id FROM "WeaponImage" WHERE path = ?',
                                 (relpath(variant['local_image']),)).fetchone()[0]
    print(f'{relpath(variant["local_image"])}: id {weapon_image_id}')

    values = {'name': weapon_name_id}
    for key, value in variant.items():
        if key == 'class':
            values[key] = weapon_class_id
        elif key == 'quality':
            values[key] = weapon_quality_id
        elif key == 'local_image':
            values['image'] = weapon_image_id
        elif key == 'homemade':
            values[key] = 1 if variant[key] else 0
        else:
            values[key] = value

    print('=' * 10)
    print('values dict:')
    print(',\n'.join(f'{k}: {v}' for k, v in values.items()))
    print('=' * 10)

    columns_count = len(values.keys())
    insert_statement = 'INSERT INTO "Weapon" (%s)' % ', '.join(key for key in values.keys()) + \
                       ' VALUES (%s)' % ', '.join('?' * columns_count)
    print('insert statement:')
    print(insert_statement)
    insert_stmt_values = list(values.values())
    assert len(insert_stmt_values) == columns_count, "Length mismatch between keys and values lengths while " \
                                                     f"inserting weapons into the database! keys = {columns_count}" \
                                                     f"values = {len(values.values())}, expected {columns_count}."
    print('inserting:')
    pprint(tuple(insert_stmt_values))
    try:
        db.execute(insert_statement, tuple(insert_stmt_values))
    except:
        print_exc_plus(frames_to_print=5, item_limit=10)


def ensure_schema(db):
    if user_version(db) == 0:
        names_schema = make_table_schema('WeaponName', keys=weapon_name_keys, unique_colname='name')
        class_schema = make_table_schema('WeaponClass', keys=weapon_class_keys, unique_colname='name')
        quality_schema = make_table_schema('WeaponQuality', keys=weapon_quality_keys, unique_colname='name')
        image_schema = make_table_schema('WeaponImage', keys=weapon_image_keys, unique_colname='path')
        weapon_schema = make_table_schema('Weapon', keys=weapon_columns, foreign_keys=weapon_foreign_keys)
        full_schema = '\n'.join([names_schema, class_schema, quality_schema, image_schema, weapon_schema,
                                 'PRAGMA foreign_keys = ON;',
                                 'PRAGMA user_version=1;'])
        print(full_schema)
        cursor = db.cursor()
        cursor.execute(full_schema)
    else:
        print('Using current schema. Delete db to recreate schema for testing.')


def create_views(cursor):
    sql = """
    CREATE VIEW IF NOT EXISTS WeaponNamesByClass(name, type)
    AS 
        SELECT DISTINCT WeaponName.name, WeaponClass.name
        FROM Weapon
        JOIN WeaponName ON Weapon.name=WeaponName.id
        JOIN WeaponClass ON Weapon.class=WeaponClass.id;\n
    """
    sql += """
    CREATE VIEW IF NOT EXISTS WeaponNamesByQuality(name, quality)
    AS 
        SELECT DISTINCT WeaponName.name, WeaponQuality.name
        FROM Weapon
        JOIN WeaponName ON Weapon.name=WeaponName.id
        JOIN WeaponQuality ON Weapon.quality=WeaponQuality.id;\n
    """
    sql += """
    CREATE VIEW IF NOT EXISTS WeaponNamesByQualityAndImage(name, quality, path)
    AS 
        SELECT DISTINCT WeaponName.name, WeaponQuality.name, WeaponImage.path
        FROM Weapon
        JOIN WeaponName ON Weapon.name=WeaponName.id
        JOIN WeaponQuality ON Weapon.quality=WeaponQuality.id
        JOIN WeaponImage ON Weapon.image=WeaponImage.id;\n
    """
    cursor.execute(sql)


def clean_db(cursor):
    sql = """DELETE FROM Weapon;
    REINDEX Weapon;
    DELETE FROM WeaponName;
    REINDEX WeaponName;
    DELETE FROM WeaponClass;
    REINDEX WeaponClass;
    DELETE FROM WeaponQuality;
    REINDEX WeaponQuality;
    DELETE FROM WeaponImage;
    REINDEX WeaponImage;"""
    cursor.execute(sql)


if __name__ == '__main__':
    args = handle_args(argv)

    debug = False
    verbose = False
    if args.debug == "on" or args.debug == "true":
        debug = True
    elif args.debug == "off" or args.debug == "false":
        debug = False
    elif args.debug == "verbose":
        verbose = True

    setup_logging(debug, verbose)

    URLs = get_weapon_pages()

    weapon_names = set()

    complete_data = {}
    for i, URL in enumerate(URLs):
        print(f"Processing {i + 1}/{len(URLs)}: {URL}")
        data = process_page(URL, debug)
        name = URL.split('/')[-1]
        weapon_names.add(name.replace('%27', "'"))
        complete_data[name] = data

    print('=' * 10)
    print('Processing complete')
    print('=' * 10)

    if verbose:
        for k, v in complete_data.items():
            print(f'key = {k}\nvalue =', end=' ')
            pprint(v)

    print('Weapon names:')
    pprint(weapon_names)

    possible_data_keys = collect_possible_data_keys(complete_data)
    print('Weapon Stats:')
    pprint(possible_data_keys)

    possible_classes = collect_possible_weapon_classes(complete_data)
    # holed_sabre does not have a class on the website, which ends up adding an empty string here
    possible_classes.discard('')
    print('Weapon Classes:')
    pprint(possible_classes)

    possible_qualities = collect_possible_weapon_quality_keys(complete_data)
    print('Weapon Qualities:')
    pprint(possible_qualities)

    image_paths = collect_possible_weapon_image_keys(complete_data)
    print('Weapon Images:')
    pprint(image_paths)

    # note: holed sabre does not have a class on the website, so we manually set it here
    for variant in complete_data['Holed_Sabre']:
        variant['class'] = 'Sabre class'

    connection = apsw.Connection("KenshiData")
    # connection.enableloadextension(True)
    # connection.loadextension(r"C:\Users\Bobbias\AppData\Local\Programs\Python\Python310\DLLs\fileio.dll",
    #                          "sqlite3_fileio_init")
    cursor = connection.cursor()

    # ensure schema before inserting data
    ensure_schema(connection)

    # delete and reindex all data, to prevent re-adding pre-existing data
    clean_db(cursor)

    # begin inserting data
    print('=' * 10)
    print('SQL INSERT statements')
    print('=' * 10)

    weapon_names_query = insert_weapon_names(weapon_names)
    cursor.execute(weapon_names_query)
    print(weapon_names_query)
    print('=' * 10)

    weapon_classes_query = insert_weapon_classes(possible_classes)
    cursor.execute(weapon_classes_query)
    print(weapon_classes_query)
    print('=' * 10)

    weapon_qualities_query = insert_weapon_qualities(possible_qualities)
    cursor.execute(weapon_qualities_query)
    print(weapon_qualities_query)
    print('=' * 10)

    weapon_images_query = insert_weapon_images(image_paths)
    cursor.execute(weapon_images_query)
    print(weapon_images_query)
    print('=' * 10)

    # begin inserting all weapons
    insert_weapons(cursor, complete_data)
