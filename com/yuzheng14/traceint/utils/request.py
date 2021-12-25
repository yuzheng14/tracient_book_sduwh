import time
import traceback
from typing import Tuple

import requests
import websocket
from ddddocr import DdddOcr

from com.yuzheng14.traceint.utils.request_utils.request import Activity, get_para_and_headers, get_resp, \
    post, get_prereserve_libLayout, verify_cookie, get_SToken, get_captcha_code_website, \
    get_captcha_image, verify_captcha, save, reserve_floor, queue_init, get_task, get_task_id
from com.yuzheng14.traceint.utils.utils import log, log_info, save_unrecognized_image, \
    save_recognized_image, get_lib_id, wait_time


def pass_captcha(cookie: str) -> str:
    """进行验证码验证,并返回websocket连接地址

    Args:
        cookie (str): header中的cookie

    Returns:
        str: websocket连接地址
    """

    ocr = DdddOcr()

    # 获取验证码的code和网址，并获取图片二进制信息
    captcha_code, captcha_website = get_captcha_code_website(cookie)
    image_byte = get_captcha_image(captcha_website)

    # ocr识别验证码
    captcha = ocr.classification(image_byte)
    log_info(f'识别验证码为{captcha}')

    # 获取验证验证码是否成功以及获得ws_url地址
    verify_result, ws_url = verify_captcha(cookie, captcha, captcha_code)
    while not verify_result:
        log_info(f'{captcha_code}尝试失败，保存验证码图片后开始下一次尝试')
        save_unrecognized_image(image_byte, captcha_code, captcha_website)

        # 获取验证码的code和网址，并获取验证码图片二进制信息
        captcha_code, captcha_website = get_captcha_code_website(cookie)
        image_byte = get_captcha_image(captcha_website)

        # 识别验证码
        captcha = ocr.classification(image_byte)
        log_info(f'识别验证码为{captcha}')
        verify_result, ws_url = verify_captcha(cookie, captcha, captcha_code)

    log_info(f'验证码尝试成功，验证码为{captcha}')
    save_recognized_image(image_byte, captcha, captcha_code, captcha_website)
    return ws_url


def pass_queue(queue_url: str, ws_url: str, need_captcha: bool, need_queue: bool) -> websocket._core.WebSocket:
    """
    通过排队
    Args:
        queue_url: 排队链接
        ws_url: websocket连接
        need_captcha: 是否需要验证验证码
        need_queue: 是否需要排队
    """
    ws = None
    try:
        if need_captcha or need_queue:
            log('当前需要排队，即将开始排队')
            log_info(f'连接地址{ws_url}')
            ws = websocket.create_connection(ws_url, timeout=30)
            log_info('create_connection连接成功')
    except Exception:
        log_info(f'\n{traceback.format_exc()}')
        log_info('create_connection连接异常')

    resp_queue = requests.get(queue_url)
    queue_num = int(resp_queue.content)
    log(f'前方排队{queue_num}人')
    while queue_num > 0:
        log_info(f'前方排队{queue_num}人')
        if queue_num > 100:
            time.sleep(2)
        resp_queue = requests.get(queue_url)
        queue_num = int(resp_queue.content)
    log_info(f'前方排队{queue_num}人')
    return ws


def pass_save(cookie: str, floor: int, often_seat: int, reverse: bool) -> str:
    """
    预定座位过程，成功则返回预定座位号
    Args:
        cookie: headers中的cookie
        floor: 楼层
        often_seat: 常用座位号
        reverse: 是否倒序

    Returns:
        预定座位号
    """
    lib_id = get_lib_id(floor)
    # 获取10楼的座位信息
    seats = get_prereserve_libLayout(cookie, lib_id)
    seats.sort(key=lambda s: abs(int(s['name']) - often_seat), reverse=reverse)
    # 预定座位
    for seat in seats:
        if not seat["status"]:
            log_info(f"开始预定{seat['name']}号")
            if save(cookie, seat['key'], lib_id):
                log_info(f"预定成功，座位为{seat['name']}号")
                return seat['name']
        else:
            log_info(f"{seat['name']}号座位已有人")


def wait_for_start(cookie: str) -> Tuple[bool, bool, bool, str, str]:
    """
    等待明日预约开始时间并初始化数据
    Args:
        cookie: headers中的cookie

    Returns:
        tuple: 按顺序为cookie_ok, need_captcha, need_queue, ws_url, queue_url
    """
    if not verify_cookie(cookie):
        log_info('cookie无效，请重新输入cookie')
        return False, False, False, '', ''
    # 在开始明日预约前的1分钟确认cookie是否有效
    log('开始等待验证cookie时间')
    wait_time(12, 29)
    if not verify_cookie(cookie):
        log_info('cookie无效，请重新输入cookie')
        return False, False, False, '', ''
    else:
        log('cookie有效，请等待预定时间')

    # 等待明日预约开始
    log('开始等待预定时间')
    wait_time(12, 30)
    need_captcha, need_queue, ws_url, queue_url = queue_init(cookie)
    return True, need_captcha, need_queue, ws_url, queue_url


def wait_for_reserve(cookie: str) -> bool:
    """
    等待捡漏开始
    Args:
        cookie: headers中的cookie

    Returns:
        bool: true为cookie验证成功
    """
    if not verify_cookie(cookie):
        log_info('cookie无效，请重新输入cookie')
        return False
    # 在开始明日预约前的1分钟确认cookie是否有效
    log('开始等待验证cookie时间')
    wait_time(6, 59)
    if not verify_cookie(cookie):
        log_info('cookie无效，请重新输入cookie')
        return False
    else:
        log('cookie有效，请等待预定时间')

    # 等待明日预约开始
    log('开始等待预定时间')
    wait_time(7, 00)
    return True


def pass_reserve(cookie: str, often_floor: int, strict_mode: bool, reserve: bool) -> str:
    """
    通过捡漏
    Args:
        cookie: headers中的cookie
        often_floor: 常用楼层
        strict_mode: 是否为严格模式，默认为true，false则为遍历全部楼层
        reserve: 是否倒序

    Returns:
        成功则返回座位号，否则返回空字符串
    """
    seat = reserve_floor(cookie, often_floor, reserve)
    if seat != '':
        return seat
    # 如果不是严格模式，则遍历全部楼层
    if not strict_mode:
        floor = [_ for _ in range(1, 15) if _ != often_floor]
        floor.sort(key=lambda f: abs(f - often_floor))
        for i in floor:
            seat = reserve_floor(cookie, get_lib_id(i), reserve)
            if seat != '':
                return seat
    return ''


def pass_reserveCancle(cookie: str) -> bool:
    """
    退座
    Args:
        cookie: headers中的cookie

    Returns:
        true为退座成功
    """
    para, headers = get_para_and_headers(Activity.reserveCancle, cookie)
    para['variables']['sToken'] = get_SToken(cookie)
    resp = post(para, headers)
    try:
        resp = resp.json()
        if 'error' not in resp:
            return True
        log_info("reserveCancle发生错误")
        log_info(_json=resp)
    except ValueError as value_exc:
        log_info('\n' + traceback.format_exc())
        log_info("reserveCancle时无json")
        log_info(resp.content)
        raise value_exc
    except KeyError as key_exc:
        log_info('\n' + traceback.format_exc())
        log_info("reserveCancle时无json无数据")
        log_info(resp)
        raise key_exc
    except Exception as e:
        log_info('\n' + traceback.format_exc())
        log_info("reserveCancle时发生其他异常")
        raise e


def wait_to_cancel(cookie: str) -> bool:
    """
    等待退座
    Args:
        cookie: headers中的cookie

    Returns:
        true为cookie失效
    """
    if not verify_cookie(cookie):
        log_info('cookie失效，请输入有效cookie后重试')
        return False

    log('开始等待验证cookie时间')
    wait_time(22, 29)
    if not verify_cookie(cookie):
        log_info('cookie无效，请重新输入cookie')
        return False
    else:
        log_info('cookie有效，请等待预定时间')

    log('等待固定时间')

    wait_time(22, 30)
    return True


def have_seat(cookie: str) -> bool:
    """
    判断当前是否有座位
    Args:
        cookie: headers中的cookie

    Returns:
        true为有座位
    """
    resp = get_resp(Activity.index, cookie)
    try:
        resp = resp.json()
        return resp['data']['userAuth']['reserve']['reserve'] is not None
    except ValueError as value_exc:
        log_info('\n' + traceback.format_exc())
        log_info("have_seat时无json")
        log_info(resp.content)
        raise value_exc
    except Exception as e:
        log_info('\n' + traceback.format_exc())
        log_info("have_seat时发生其他异常")
        raise e


def is_sign(cookie: str) -> bool:
    """
    是否签到
    Args:
        cookie: headers中的cookie

    Returns:
        true为已经签到
    """
    task = get_task(cookie)
    while task is None:
        task = get_task(cookie)
    return task['status'] == 2


def pass_sign(cookie: str) -> bool:
    """
    通过签到
    Args:
        cookie: headers中的cookie

    Returns:
        true为签到成功
    """
    para, headers = get_para_and_headers(Activity.done, cookie)
    para['variables']['user_task_id'] = get_task_id(cookie)
    resp = post(para, headers)
    try:
        resp = resp.json()
        if 'errors' in resp:
            log_info('errors时cookie可能过期')
            log_info(_json=resp)
        return resp['data']['userAuth']['credit']['done']
    except ValueError as value_exc:
        log_info(f'\n{traceback.format_exc()}')
        log_info('pass_sign时无json')
        log_info(resp.content)
        raise value_exc
    except KeyError as key_exc:
        log_info(f'\n{traceback.format_exc()}')
        log_info('pass_sign时json无数据')
        log_info(_json=resp)
        raise key_exc
    except Exception as exc:
        log_info(f'\n{traceback.format_exc()}')
        log_info('pass_sign时发生其他异常')
        raise exc
