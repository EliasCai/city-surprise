import gradio as gr
import leafmap.foliumap as leafmap
import folium
from typing import List, Dict, Optional, Tuple
import random
import requests
import json
import re
import time

# ==================== Dify工作流配置 ====================
DIFY_API_URL = "https://api.dify.ai/v1/workflows/run"
DIFY_API_KEY = "app-oAbK9afxJdLcMto7aAE5F5BW"
DIFY_USER = "abc-123"

# ==================== 预设地址坐标（用于起点定位） ====================
preset_addresses = {
    "苏州高铁新城": (31.3968, 120.5954),
    "苏州工业园区": (31.3280, 120.6950),
    "观前街": (31.3105, 120.6212),
    "平江路": (31.3140, 120.6205),
    "金鸡湖畔": (31.3205, 120.6905),
    "山塘街": (31.3050, 120.5950),
}

# ==================== 高德API调用函数 ====================
def get_walking_route(origin: str, destination: str) -> Optional[dict]:
    """
    调用高德地图步行路线规划API
    格式：origin="经度,纬度", destination="经度,纬度"
    """
    url = "https://restapi.amap.com/v3/direction/walking"
    params = {
        "origin": origin,
        "destination": destination,
        "key": "278641d30cc5bc2acfc080fe5d9ad884"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "1" and data.get("infocode") == "10000":
            return data
        else:
            error_msg = data.get("info", "未知错误")
            print(f"API调用失败: {error_msg}")
            return None
    except Exception as e:
        print(f"请求异常: {e}")
        return None

def parse_route_data(route_data: dict) -> Tuple[List[List[float]], Optional[List[float]], Optional[List[float]], dict]:
    """
    解析路线数据，提取polyline点和路线信息
    返回: (路线点列表, 起点坐标, 终点坐标, 路线信息)
    坐标格式: [纬度, 经度]
    """
    if not route_data or "route" not in route_data:
        return [], None, None, {}

    route = route_data["route"]
    paths = route.get("paths", [])

    if not paths:
        return [], None, None, {}

    path = paths[0]
    steps = path.get("steps", [])

    # 提取所有polyline点
    route_points = []
    for step in steps:
        polyline = step.get("polyline", "")
        if polyline:
            points = polyline.split(";")
            for point in points:
                if point:
                    try:
                        lon, lat = point.split(",")
                        route_points.append([float(lat), float(lon)])  # folium需要[纬度, 经度]
                    except ValueError:
                        continue

    # 路线统计信息
    route_info = {
        "distance": path.get("distance", "0"),  # 总距离（米）
        "duration": path.get("duration", "0"),  # 总时长（秒）
        "step_count": len(steps)
    }

    return route_points, None, None, route_info

# ==================== Dify工作流调用函数 ====================

DEFAULT_JSON = \
{
  "address": [
    {
      "name": "苏州平江路",
      "geo": "120.633318,31.315931",
      "intro": "",
      "hour": 0.0,
      "distance": 0
    },
    {
      "name": "中国昆曲博物馆",
      "geo": "120.634500,31.317200",
      "intro": "中张家巷14号的专题博物馆，展示600年昆曲历史，含珍贵戏服、古籍及全息水袖表演体验",
      "hour": 1.5,
      "distance": 280
    },
    {
      "name": "玄妙观",
      "geo": "120.625000,31.312000",
      "intro": "始建于西晋的江南第一道观，三清殿为宋代遗构，观内银杏树龄超800年",
      "hour": 1.0,
      "distance": 650
    },
    {
      "name": "苏州博物馆(本馆)",
      "geo": "120.628000,31.320000",
      "intro": "贝聿铭设计的园林式博物馆，镇馆之宝为秘色瓷莲花碗，片石假山借景北寺塔",
      "hour": 2.0,
      "distance": 780
    },
    {
      "name": "双塔市集",
      "geo": "120.630000,31.305000",
      "intro": "百年菜场改造的网红市集，苏式点心铺与文创店融合，登顶可拍双塔倒影",
      "hour": 1.5,
      "distance": 1100
    }
  ]
}

def stream_workflow(input_user: str) -> Optional[Dict]:
    """
    调用Dify工作流获取路线规划数据
    """
    payload = json.dumps({
        "inputs": {
            "input_user": input_user
        },
        "response_mode": "streaming",
        "user": DIFY_USER
    })

    headers = {
        'Authorization': f'Bearer {DIFY_API_KEY}',
        'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Host': 'api.dify.ai',
        'Connection': 'keep-alive'
    }

    try:
        response = requests.post(DIFY_API_URL, headers=headers, data=payload, stream=True, timeout=300)
        response.raise_for_status()

        collected_text = []
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith('data: '):
                json_data = line[6:]  # Remove "data: " prefix
                try:
                    event_data = json.loads(json_data)
                    if event_data.get('event') == 'text_chunk':
                        text_content = event_data.get('data', {}).get('text', '')
                        if text_content:
                            collected_text.append(text_content)
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
                    print(f"Raw data: {json_data}")

        full_text = ''.join(collected_text)

        # 提取JSON内容
        match = re.search(r'(\{.*\})', full_text, re.DOTALL)
        if match:
            json_string = match.group(1)
            try:
                parsed_json = json.loads(json_string)
                return parsed_json
            except json.JSONDecodeError as e:
                print(f"JSON decode error after extraction: {e}")
                print(f"Extracted string: {json_string}")
                return DEFAULT_JSON # None
        else:
            print("No JSON found in the response")
            print(full_text)
            return DEFAULT_JSON # None

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return DEFAULT_JSON # None

# ==================== 工具函数 ====================
def generate_route_description_from_json(route_data: Dict, transport_mode: str):
    """从Dify返回的JSON生成路线说明"""
    if not route_data or "address" not in route_data:
        return "**⚠️ 未能生成有效路线数据**"

    addresses = route_data["address"]
    if len(addresses) < 2:
        return "**⚠️ 路线数据不完整，至少需要起点和一个打卡点**"

    # 第一个是起点
    start_point = addresses[0]
    start_address = start_point["name"]

    # 后续是打卡点
    pois = addresses[1:]

    total_time = 30  # 起点准备时间
    total_distance = 0

    desc = f"## 🎯 路线总览\n"
    desc += f"**起点**：{start_address}  \n"
    desc += f"**出行方式**：{transport_mode}  \n"
    desc += f"**打卡点数量**：{len(pois)}个  \n"

    desc += f"## 🗺️ 详细行程\n"

    for i, poi in enumerate(pois, 1):
        travel_time = random.randint(10, 25)
        stay_time = int(float(poi.get("hour", 0.5)) * 60) or random.randint(25, 45)
        distance = int(poi.get("distance", 0))
        total_time += travel_time + stay_time
        total_distance += distance

        desc += f"### 📍 第{i}站：{poi['name']}\n"
        # desc += f"**地址**：{poi['geo']}  \n"
        desc += f"**预计停留**：{stay_time}分钟  \n"
        # desc += f"**距离起点**：{distance}米  \n"
        desc += f"**简介**：{poi['intro'] or '暂无介绍'}\n\n"

    total_time_str = f"{total_time//60}小时{total_time%60}分钟" if total_time > 60 else f"{total_time}分钟"
    total_distance_km = total_distance / 1000

    desc = desc.replace(" **打卡点数量**", f" **预计总时长**：{total_time_str}  \n**预计总距离**：约{total_distance_km:.1f}公里  \n**实际步行距离可能有所不同**  \n **打卡点数量**")

    return desc

# ==================== 核心地图生成函数 ====================
def create_exploration_map_from_json(route_data: Dict, transport_mode: str = "步行 🚶"):
    """
    从Dify返回的JSON创建探索路线图
    """
    if not route_data or "address" not in route_data:
        return create_empty_map()

    addresses = route_data["address"]
    if len(addresses) < 1:
        return create_empty_map()

    # 解析所有地址的坐标
    all_coords = []
    valid_addresses = []

    for addr in addresses:
        geo_str = addr.get("geo", "")
        if geo_str:
            try:
                lon, lat = geo_str.split(",")
                all_coords.append([float(lat), float(lon)])
                valid_addresses.append(addr)
            except (ValueError, AttributeError):
                continue

    if len(all_coords) == 0:
        return create_empty_map()

    # 创建地图，以第一个点（起点）为中心
    start_lat, start_lon = all_coords[0]
    m = leafmap.Map(
        location=(start_lat, start_lon),
        tiles="https://wprd01.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=1&style=7",
        attr="高德地图",
        zoom_start=14,
    )

    # 标记起点
    start_point = valid_addresses[0]
    folium.Marker(
        location=all_coords[0],
        popup=f"<b>起点</b><br>{start_point['name']}<br>{start_point['geo']}",
        icon=folium.Icon(color="red", icon="play", prefix="fa")
    ).add_to(m)

    # 标记打卡点
    colors = ["green", "blue", "purple", "orange", "darkred", "lightgreen", "lightblue", "pink"]
    for i, (addr, coord) in enumerate(zip(valid_addresses[1:], all_coords[1:]), 1):
        icon = folium.Icon(color=colors[i % len(colors)], icon=f"{i}", prefix="fa")
        popup = f"<b>第{i}站：{addr['name']}</b>"# <br>{addr['geo']}<br>距离起点：{addr.get('distance', 0)}米"

        folium.Marker(
            location=coord,
            popup=popup,
            icon=icon
        ).add_to(m)

    # ==================== 新增：步行路线规划 ====================
    # 如果出行方式是步行且有多个点，调用高德API绘制真实步行路线
    if transport_mode == "步行 🚶" and len(all_coords) >= 2:
        for i in range(len(all_coords) - 1):
            # 获取当前点和下一点的坐标（[纬度, 经度]格式）
            current_coord = all_coords[i]
            next_coord = all_coords[i + 1]

            # 转换为高德API需要的格式：经度,纬度
            origin = f"{current_coord[1]},{current_coord[0]}"
            destination = f"{next_coord[1]},{next_coord[0]}"

            # 调用高德步行路线规划API
            route_data = get_walking_route(origin, destination)

            if route_data:
                route_points, _, _, route_info = parse_route_data(route_data)
                if route_points:
                    # 成功获取路线，绘制到地图上
                    distance_km = int(route_info.get('distance', 0)) / 1000
                    duration_min = int(route_info.get('duration', 0)) // 60

                    # 使用不同颜色区分每段路线
                    route_color = f"#{hash(str(i)) % 0xFFFFFF:06x}"

                    folium.PolyLine(
                        locations=route_points,
                        color=route_color,
                        weight=4,
                        opacity=0.8,
                        popup=f"步行 第{i+1}段<br>距离: {distance_km:.2f} km<br>时间: {duration_min} 分钟"
                    ).add_to(m)
                else:
                    # API返回数据但无路线点，用直线连接
                    folium.PolyLine(
                        locations=[current_coord, next_coord],
                        color="gray",
                        weight=2,
                        opacity=0.6,
                        popup="直线连接（无路线数据）"
                    ).add_to(m)
            else:
                # API调用失败，用直线连接
                folium.PolyLine(
                    locations=[current_coord, next_coord],
                    color="gray",
                    weight=2,
                    opacity=0.6,
                    popup="直线连接（API调用失败）"
                ).add_to(m)

            # 控制API调用频率，避免触发限流
            time.sleep(0.1)

    # 自动调整地图视野
    if len(all_coords) > 1:
        try:
            bounds = [[min(c[0] for c in all_coords), min(c[1] for c in all_coords)],
                     [max(c[0] for c in all_coords), max(c[1] for c in all_coords)]]
            m.fit_bounds(bounds, padding=[30, 30])
        except:
            pass

    return m.to_gradio()

def create_empty_map():
    """创建空地图（备用）"""
    m = leafmap.Map(
        location=(31.3280, 120.6950),
        tiles="https://wprd01.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=1&style=7",
        attr="高德地图",
        zoom_start=12,
    )
    return m.to_gradio()

# ==================== 主处理函数 ====================
def handle_generate_click(start_address, style_tags, transport_mode):
    """处理生成按钮点击 - 集成Dify工作流"""
    try:
        # 验证输入
        if not start_address:
            return create_empty_map(), "**⚠️ 请输入起点地址**"

        if not style_tags:
            return create_empty_map(), "**⚠️ 请至少选择一种路线风格**"

        if len(style_tags) > 3:
            return create_empty_map(), "**⚠️ 路线风格最多选择3种哦**"

        # 构建Dify输入字符串
        input_user = f'start_address="{start_address}", interests={json.dumps(style_tags, ensure_ascii=False)}'

        # 调用Dify工作流
        route_data = stream_workflow(input_user)

        if not route_data:
            return create_empty_map(), "**⚠️ Dify工作流调用失败，请检查配置**"

        # 生成地图和说明
        route_map = create_exploration_map_from_json(route_data, transport_mode)
        route_desc = generate_route_description_from_json(route_data, transport_mode)

        return route_map, route_desc

    except Exception as e:
        print(f"处理错误: {e}")
        return create_empty_map(), f" **⚠️ 生成路线时出错：{str(e)}**"

# ==================== Gradio界面 ====================
# 构建Gradio界面
with gr.Blocks(
    title="漫游盲盒 - City Surprise",
    css="""
    .gradio-container {font-family: 'Microsoft YaHei', sans-serif; max-width: 1400px; margin: 0 auto;}
    .title {text-align: center; color: #1e88e5; margin-bottom: 10px; font-size: 2.5rem !important;}
    .subtitle {text-align: center; color: #666; margin-bottom: 30px; font-size: 1.2rem;}
    .input-panel {background: #f5f7fa; padding: 20px; border-radius: 10px; min-height: 500px;}
    .generate-btn {background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; color: white !important; border: none !important; font-weight: bold;}
    #map-container {height: 500px !important;}
    """
) as demo:

    # 顶部产品介绍
    gr.Markdown("# 🎁 漫游盲盒 City Surprise", elem_classes="title")
    gr.Markdown(
        "将探索的乐趣交还给未知｜AI驱动的城市微冒险生成器\n\n"
        "厌倦了千篇一律的城市生活？让AI为你策划一场充满惊喜的城市探索之旅",
        elem_classes="subtitle"
    )

    # 主交互区域
    with gr.Row():
        # 左侧输入面板
        with gr.Column(scale=1, elem_classes="input-panel"):
            gr.Markdown("### 🚀 出发设置")

            # 起点输入区域
            with gr.Group():
                gr.Markdown("**📍 起点地址**")
                address_input = gr.Textbox(
                    label="",
                    placeholder="请输入您的起点地址，如：苏州平江路",
                    value="苏州平江路",
                    lines=1
                )
                address_dropdown = gr.Dropdown(
                    choices=list(preset_addresses.keys()),
                    label="快速选择",
                    value="苏州平江路",
                    filterable=True
                )

            # 路线风格选择
            style_checkboxes = gr.CheckboxGroup(
                choices=["文艺", "美食", "自然", "历史", "潮流", "小众", "摄影", "咖啡", "古建", "博物馆"],
                label="🎨 路线风格（建议选1-3个）",
                value=["文艺", "历史"],
                info="选择你感兴趣的探索主题"
            )

            # 出行方式选择
            transport_radio = gr.Radio(
                choices=["步行 🚶", "骑行 🚴", "公共交通 🚌"],
                label="🚦 出行方式",
                value="步行 🚶",
                info="步行模式将显示真实路径规划"
            )

            # 生成按钮
            generate_btn = gr.Button(
                "🎲 开启盲盒，生成专属路线",
                variant="primary",
                size="lg",
                elem_classes="generate-btn"
            )

        # 右侧地图展示
        with gr.Column(scale=2):
            map_output = gr.HTML(
                value=create_empty_map(),
                label="探索路线图",
                show_label=True,
                elem_id="map-container"
            )

    # 路线详情区域
    with gr.Group():
        gr.Markdown("### 📋 路线详情")
        route_description_output = gr.Markdown(
            "**欢迎使用漫游盲盒！**\n\n"
            "请设置您的探索偏好，点击\"开启盲盒\"按钮生成专属路线。\n\n"
            "💡 **使用提示**：\n"
            "- 起点支持直接输入或下拉选择\n"
            "- 路线风格建议选1-3个\n"
            "- 选择\"步行\"模式可看到真实的步行路径规划\n"
            "- 系统将通过AI智能体为您定制专属路线"
        )

    # 事件绑定
    address_dropdown.change(fn=lambda x: x, inputs=address_dropdown, outputs=address_input)

    generate_btn.click(
        fn=handle_generate_click,
        inputs=[address_input, style_checkboxes, transport_radio],
        outputs=[map_output, route_description_output]
    )

# 启动应用
if __name__ == "__main__":
    demo.launch(show_api=False, share=True, debug=True)