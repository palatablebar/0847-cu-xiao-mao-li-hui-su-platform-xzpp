from flask import jsonify


MESSAGES = {
    "EMPTY_FILE": "文件为空",
    "BLANK_FILE": "文件只有空白",
    "HEADER_ONLY": "文件只有表头",
    "HEADER_MISMATCH": "表头与本项目字段不一致",
    "UNCLOSED_QUOTE": "引号未闭合，文件已拒收",
    "TOO_MANY_ROWS": "数据行超过上限",
    "FILE_TOO_LARGE": "文件超过大小上限",
    "KEY_MISSING": "主键为空",
    "CONFLICT_DUPLICATE": "同一键存在冲突内容",
    "SAMPLE_UNKNOWN": "样例不存在",
    "STAGE_UNKNOWN": "阶段不存在",
    "RUN_NOT_FOUND": "批次不存在",
    "STALE_REVIEW": "批次已被更新，请刷新后复核",
    "GATE_BLOCKED": "存在阻断项，不能签发",
    "NOT_APPROVED": "批次尚未签发",
    "BAD_REQUEST": "请求内容不完整",
    "CAMPAIGN_NOT_FOUND": "活动不存在",
    "ORDER_NOT_FOUND": "订单不存在",
    "ORDER_CONFLICT": "订单一经提交不可改写，请换新订单号",
    "ORDER_LOSS": "用券后亏损的订单不能签发",
    "ORDER_CANCELLED": "订单已取消，不能签发",
    "QUOTA_UNAVAILABLE": "额度不足，订单仍在候补",
    "BAD_RECEIVED_AT": "接单时间无法解析",
    "INVALID_QUOTA_CENTS": "活动额度必须为非负整数",
    "INVALID_LINE_QTY": "数量必须为正整数",
    "INVALID_SELL_PRICE_CENTS": "售价必须为非负整数",
    "INVALID_UNIT_COST_CENTS": "单件成本必须为非负整数",
    "INVALID_SUPPLIER_FUND_CENTS": "供应商出资必须为非负整数",
    "INVALID_COUPON_CENTS": "券金额必须为非负整数",
    "FUND_OVER_COST": "供应商出资超过成本",
    "COUPON_OVER_REVENUE": "券金额超过行收入",
}


class DomainIssue(Exception):
    def __init__(self, code: str, status: int = 400, detail: str | None = None):
        self.code = code
        self.status = status
        self.detail = detail
        super().__init__(code)


def error_response(exc: DomainIssue):
    return jsonify(error=exc.detail or MESSAGES.get(exc.code, "请求无法处理"), code=exc.code), exc.status
