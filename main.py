from PIL import Image, ImageOps
from itertools import groupby
from scipy.ndimage import label
from scipy.ndimage import distance_transform_edt
import numpy as np

filename = "example.png"

with Image.open(filename) as img:
    img.load()
    img = img.convert('RGB')

img = ImageOps.expand(img, border=1, fill="#396B88")

data = np.array(img)

h=img.height
w=img.width

result = np.zeros((h, w), dtype=np.uint16)

# море
white  = (
    (data[:, :, 0] == 57) &
    (data[:, :, 1] == 107) &
    (data[:, :, 2] == 136)
)

# граница
black = (
    (
            (data[:, :, 0] == 48) &
            (data[:, :, 1] == 48) &
            (data[:, :, 2] == 48)
    )
        |
    (
            (data[:, :, 0] == 0) &
            (data[:, :, 1] == 0) &
            (data[:, :, 2] == 0)
    )
)

result[white] = 0
result[black] = 1
result[~white & ~black] = 4


# defining separate tiles (voronoi)
mask = (result == 4)

labeled, num_features = label(mask)

new_values = labeled + 5

result[mask] = new_values[mask]

black_mask = (result == 1)
colored_mask = (result >= 5)

# Расстояние только внутри чёрных пикселей
# Белые (море) — недостижимы, ставим их как барьер

traversable = black_mask | colored_mask

_, nearest = distance_transform_edt(~colored_mask & traversable | ~traversable,
                                     return_indices=True)

voronoi = result.copy()
# Перекрашиваем ТОЛЬКО чёрные пиксели, белые не трогаем
voronoi[black_mask] = result[nearest[0], nearest[1]][black_mask]


# deleting small tiles
values, counts = np.unique(voronoi, return_counts=True)
rare_values = values[counts < 5]
voronoi[np.isin(voronoi, rare_values)] = 0

# filling in the blanks
def smooth_from_min_fast(arr, fixed_max=5):
    arr = np.asarray(arr)
    res = arr.copy()

    # уникальные значения > fixed_max
    vals = np.unique(arr)
    vals = vals[vals > fixed_max]

    if len(vals) == 0:
        return res

    start = vals.min()

    # старые значения -> новые подряд без дырок
    # пример: [200,202,250] -> [200,201,202]
    new_vals = np.arange(start, start + len(vals))

    # создаём lookup table
    max_val = arr.max()
    lut = np.arange(max_val + 1)

    lut[vals] = new_vals

    # применяем мгновенно ко всему массиву
    return lut[arr]

voronoi = smooth_from_min_fast(voronoi)

result = voronoi.copy()

# square_img = Image.fromarray(result)
# square_img.save("square.png")

# initialization of tiles
tiles = []
tiles_color = []
for i in range(voronoi.max()-5):
    tiles.append([])
    tiles_color.append([])

# boundary
for i in range(1, h - 1):
    for j in range(1, w - 1):

        if voronoi[i, j] < 5:
            continue

        neighbors = [
            voronoi[i, j+1],
            voronoi[i+1, j],
            voronoi[i, j-1],
            voronoi[i-1, j]
        ]

        sides_code = "0000" # все соседи - такого же цвета соседи

        center = voronoi[i, j]

        for k in range(len(neighbors)):
            if neighbors[k] != voronoi[i, j]:
                # если другого цвета, то 1
                li = list(sides_code)
                li[k] = '1'
                sides_code = ''.join(li)

        corners_code = "0000" # нигде точки не нужны

        for k in range(4):
            if sides_code[k] == "1": # если сосед не такой же, как и точка
                li = list(corners_code)
                li[k] = '1' # нужна тут
                corners_code = ''.join(li)

                li = list(corners_code)
                li[(k+1) % 4] = '1' # и тут нужна
                corners_code = ''.join(li)
        pixel = []

        corners = [
            [i, j+1],
            [i+1, j+1],
            [i+1, j],
            [i, j]
        ]

        if corners_code == "0000":
            continue

        for k in range(4):
            if corners_code[k] == "0":
                pixel.append([-1, -1])
            else:
                pixel.append(corners[k])

        tiles[voronoi[i, j] - 6].append(pixel)

# sort pixels
new_tiles = []

print("Сгенерированы тайлы номер:")
len_of_str = 0
for num, tile in enumerate(tiles):

    for_check = tile.copy()
    new_tile = []

    current_pixel = 0
    current_corner = 0
    current_coord = [-1, -1]

    # initialize the first data
    corner_start = 2
    while True:
        coord = tile[0][corner_start]
        if coord != [-1, -1]:
            current_corner = corner_start
            current_coord = coord # первая координата, которая не нолик
            break
        corner_start = (corner_start + 1) % 4

    done = False
    while not done:

        if for_check[current_pixel][current_corner] != [-1, -1]: # если это реальная точка
            current_coord = for_check[current_pixel][current_corner] # текущая координата
            new_tile.append(current_coord) # добавили в список
            for_check[current_pixel][current_corner] = [-1, -1] # просмотрели
            current_corner = (current_corner + 1) % 4 # переместились в следующий угол
        else:
            # если пиксель пуст, то удалить его
            if for_check[current_pixel] == [[-1, -1], [-1, -1], [-1, -1], [-1, -1]]:
                for_check.pop(current_pixel)

            done = True # если цикл ничего не нашёл, то закончить
            for j, pixel in enumerate(for_check):
                for k, coord in enumerate(pixel):
                    if coord == current_coord: # если пиксель/координата продолжают "круг"
                        current_pixel = j # то поменять текущий пиксель на этот пиксель
                        current_corner = k # и текущий угол на угол
                        done = False # цикл что-то нашёл
    new_tiles.append(new_tile)
    len_of_str += len(str(num)) + 1
    print("", num, end="")
    if len_of_str >= 30:
        len_of_str = 0
        print("")

tiles = new_tiles
print("... Базовая обработка завершенна")

# more handling
for i, tile in enumerate(tiles):
    tiles[i] = [el for el, _ in groupby(tile)]

new_tiles = []
for tile in tiles:
    new_tile = []

    l = len(tile)

    for i in range(l):
        # удаление совсем лишних точек
        if tile[i-1][0] == tile[i][0] == tile[(i+1) % l][0]:
            continue
        if tile[i-1][1] == tile[i][1] == tile[(i+1) % l][1]:
            continue
        new_tile.append(tile[i])
    new_tiles.append(new_tile)
tiles = new_tiles

# colors
for i in range(1, h-1):
    for j in range(1, w-1):
        if colored_mask[i, j]:
            tiles_color[voronoi[i, j] - 6].append(img.getpixel((j, i)))

for i in range(len(tiles_color)):
    tiles_color[i] = np.array(tiles_color[i])
    if tiles_color[i].size == 0:
        tiles_color[i] = np.array([200, 200, 200], dtype=int)  # or any default color
    else:
        tiles_color[i] = np.nanmean(tiles_color[i], axis=0).astype(int)
    print("Цвет тайла №", i, " равен ", tiles_color[i])



# export to config
tile_colors = {
    i: tuple(map(int, tiles_color[i]))
    for i in range(len(tiles_color))
}

tile_anchor_points = {
    i: borders
    for i, borders in enumerate(tiles)
}

def corner_to_mc(
    cr: int, cc: int,
    src_corner: tuple[int, int],   # (row, col) — исходный угол (напр. верхний левый)
    dst_corner: tuple[int, int],   # (row, col) — исходный угол (напр. нижний правый)
    mc_src: tuple[int, int],       # (x, z) — куда отображается src_corner в MC
    mc_dst: tuple[int, int],       # (x, z) — куда отображается dst_corner в MC
) -> tuple[int, int]:
    """
    Линейное отображение угловой точки (row, col)
    из [src_corner → dst_corner] в MC-координаты [mc_src → mc_dst].
    """
    src_r, src_c = src_corner
    dst_r, dst_c = dst_corner
    mc_src_x, mc_src_z = mc_src
    mc_dst_x, mc_dst_z = mc_dst

    # Защита от деления на ноль (если диапазон вырожденный)
    t_c = (cc - src_c) / (dst_c - src_c) if dst_c != src_c else 0.0
    t_r = (cr - src_r) / (dst_r - src_r) if dst_r != src_r else 0.0

    x = mc_src_x + t_c * (mc_dst_x - mc_src_x)
    z = mc_src_z + t_r * (mc_dst_z - mc_src_z)

    return int(round(x)), int(round(z))


# export to bluemap
# from txt (3)
def build_bluemap_config(
    tile_anchor_points: dict,
    shape_y: int = 64,
    # Два угла сетки (в пикселях/ячейках)
    src_corner: tuple[int, int] = (0, 0),
    dst_corner: tuple[int, int] = (100, 100),
    # Соответствующие им MC-координаты
    mc_src: tuple[int, int] = (0, 0),
    mc_dst: tuple[int, int] = (1000, 1000),
) -> str:
    def fmt_color(r, g, b, a):
        return f"{{ r: {r}, g: {g}, b: {b}, a: {a} }}"

    def to_mc(cr, cc):
        return corner_to_mc(cr, cc, src_corner, dst_corner, mc_src, mc_dst)

    lines = [
        "marker-sets: {",

        "  numbers: {",
        '      label: "numbers"',
        "      toggleable: true",
        "      default-hidden: false",
        "      markers: {",
        "          example-html-marker: {",
        '              type: "html"',
        "              position: { x: 512, y: 75, z: 256 }",
        '              label: "Numbers"',
        '              html: "<img src=\'https://i.ibb.co/ymyVcrvN/image-23.png\'>"',
        "              sorting: 0",
        "              listed: true",
        "              classes: [",
        '                  "html3d"',
        '                  "html3d-density-0_06237449799"',
        '                  "html3d-width-16448"',
        '                  "html3d-height-15936"',
        '                  "html3d-rx--90"',
        "              ]",
        "              min-distance: 10",
        "              max-distance: 10000000",
        "          }",
        "      }",
        "  }",

        "  resources: {",
        '      label: "resources"',
        "      toggleable: true",
        "      default-hidden: false",
        "      markers: {",
        "          example-html-marker: {",
        '              type: "html"',
        "              position: { x: 512, y: 65, z: 256 }",
        '              label: "Resources"',
        '              html: "<img src=\'https://i.ibb.co/zW0tYBfp/image-22.png\'>"',
        "              sorting: 0",
        "              listed: true",
        "              classes: [",
        '                  "html3d"',
        '                  "html3d-density-0_12468624498"',
        '                  "html3d-width-16448"',
        '                  "html3d-height-15936"',
        '                  "html3d-rx--90"',
        "              ]",
        "              min-distance: 10",
        "              max-distance: 10000000",
        "          }",
        "      }",
        "  }",
        "  tiles: {",
        '    label: "Tiles"',
        "    toggleable: true",
        "    default-hidden: false",
        "    markers: {",
    ]

    for tile_id, anchors in tile_anchor_points.items():
        if len(anchors) < 3:
            continue

        r, g, b = tile_colors[tile_id][:3]
        cx, cz = to_mc(anchors[0][0], anchors[0][1])

        lines += [
            f"      tile-{tile_id}: {{",
            f'        type: "shape"',
            f"        position: {{ x: {cx}, y: {shape_y}, z: {cz} }}",
            f'        label: "Tile {tile_id}"',
            f"        shape: [",
        ]
        for cr, cc in anchors:
            mx, mz = to_mc(cr, cc)
            lines.append(f"          {{ x: {mx}, z: {mz} }}")

        mx0, mz0 = to_mc(anchors[0][0], anchors[0][1])
        lines += [
            f"          {{ x: {mx0}, z: {mz0} }}",
            f"        ]",
            f"        shape-y: {shape_y}",
            f"        depth-test: false",
            f"        line-width: 2",
            f"        line-color: {fmt_color(r, g, b, 1.0)}",
            f"        fill-color: {fmt_color(r, g, b, 0.15)}",
            f"        listed: true",
            f"        min-distance: 10",
            f"        max-distance: 10000000",
            f"      }}",
        ]

    lines += ["    }", "  }", "}"]
    return "\n".join(lines)

config_str = build_bluemap_config(
    tile_anchor_points,
    shape_y=64,
    src_corner=(0, 0),          # верхний левый пиксель сетки
    dst_corner=(h, w),      # нижний правый пиксель сетки
    mc_src=(-7712, -7712),      # куда он попадает в MC
    mc_dst=(8736, 8224),        # куда попадает нижний правый
)

with open("markers.conf", "w", encoding="utf-8") as f:
    f.write(config_str)

print("Конфиг bluemap сгенрирован!")

# export to dynmap
def build_dynmap_config(
    tile_anchor_points: dict,
    shape_y: int = 64,
    src_corner: tuple[int, int] = (0, 0),
    dst_corner: tuple[int, int] = (100, 100),
    mc_src: tuple[int, int] = (0, 0),
    mc_dst: tuple[int, int] = (1000, 1000),
    world: str = "world",
) -> str:

    def to_mc(cr, cc):
        return corner_to_mc(cr, cc, src_corner, dst_corner, mc_src, mc_dst)

    def rgb_to_dynmap_int(r, g, b):
        return (r << 16) | (g << 8) | b

    def yaml_float_list(values, indent):
        pad = " " * indent
        return "\n".join(f"{pad}- {float(v)}" for v in values)

    lines = [
        "%YAML 1.1",
        "---",
        "isSafe: true",
        "icons: {",
        "    }",
        "sets:",
        "    tiles:",
        "        hide: false",
        "        circles: {",
        "            }",
        "        deficon: default",
        "        areas:",
    ]

    for tile_id, anchors in tile_anchor_points.items():
        if len(anchors) < 3:
            continue

        r, g, b = tile_colors[tile_id][:3]
        color_int = rgb_to_dynmap_int(r, g, b)

        xs = [float(to_mc(cr, cc)[0]) for cr, cc in anchors]
        zs = [float(to_mc(cr, cc)[1]) for cr, cc in anchors]

        lines += [
            f"            Tile{tile_id}:",
            f"                fillColor: {color_int}",
            f"                world: {world}",
            f"                markup: true",
            f"                ytop: {float(shape_y)}",
            f"                fillOpacity: 0.35",
            f"                x:",
            yaml_float_list(xs, 16),
            f"                strokeWeight: 3",
            f"                z:",
            yaml_float_list(zs, 16),
            f"                label: Tile{tile_id}",
            f"                ybottom: {float(shape_y)}",
            f"                strokeColor: {color_int}",
            f"                strokeOpacity: 0.8",
        ]

    lines += [
        "        label: tiles",
        "        markers: {",
        "            }",
        "        lines: {",
        "            }",
        "        layerprio: 0",

        "    markers:",
        "        hide: false",
        "        circles: {",
        "            }",
        "        deficon: default",
        "        areas: {",
        "            }",
        "        label: Markers",
        "        markers: {",
        "            }",
        "        lines: {",
        "            }",
        "        layerprio: 0",

        "playersets: {",
        "    }",
    ]

    return "\n".join(lines)

config_str = build_dynmap_config(
    tile_anchor_points,
    shape_y=64,
    src_corner=(0, 0),
    dst_corner=(h, w),
    mc_src=(-7712, -7712),
    mc_dst=(8736, 8224),
    world="Factions",
)

with open("markers.yml", "w", encoding="utf-8") as f:
    f.write(config_str)

print("Конфиг dynmap сгенрирован!")