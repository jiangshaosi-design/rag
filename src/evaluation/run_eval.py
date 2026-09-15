"""RAG 评估运行脚本。在项目根目录执行: python -m src.evaluation.run_eval"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.evaluation.metrics import evaluate_rag, print_eval_report

TEST_CASES = [
    {
        "question": "CH32V103 微控制器的最大系统主频是多少？",
        "expected_keywords": ["72", "MHz", "主频", "系统时钟"],
    },
    {
        "question": "CH32V103 有哪些封装类型？",
        "expected_keywords": ["LQFP", "QFN", "封装", "引脚", "48", "64", "100"],
        "expected_image": True,
        "check_image": True,
    },
    {
        "question": "请介绍一下 CH32V103 的 GPIO 端口数量",
        "expected_keywords": ["GPIO", "端口", "引脚"],
    },
    {
        "question": "CH32V103 的中断系统支持多少个中断通道？",
        "expected_keywords": ["中断", "NVIC", "向量"],
    },
    {
        "question": "CH32V103 的 Flash 和 SRAM 容量分别是多少？",
        "expected_keywords": ["Flash", "SRAM", "KB", "存储"],
    },
    {
        "question": "请总结当前知识库中所有核心技术参数",
        "expected_keywords": ["参数", "特性", "规格"],
    },
    {
        "question": "系统中已上传了哪些文档？",
        "expected_keywords": [],
    },
    {
        "question": "CH32V103 的 ADC 精度和通道数是多少？",
        "expected_keywords": ["ADC", "精度", "通道", "12", "位", "bit"],
    },
    {
        "question": "文档中有哪些关于电源管理的内容？",
        "expected_keywords": ["电源", "电压", "供电", "VDD", "功耗", "低功耗"],
    },
    {
        "question": "CH32V103 的定时器有哪些类型？",
        "expected_keywords": ["定时器", "TIM", "PWM", "计数器"],
    },
]


if __name__ == "__main__":
    print("RAG 系统评估开始...")
    print(f"测试用例: {len(TEST_CASES)} 个")
    results = evaluate_rag(TEST_CASES, k=5, eval_faithfulness=True)
    print_eval_report(results)
