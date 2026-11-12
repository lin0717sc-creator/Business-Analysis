# financial_engine.py
from pydantic import BaseModel
from typing import Dict

# 定义基础假设参数（由大模型负责提取填充）
class FinancialAssumptions(BaseModel):
    initial_capital: float        # 初始资金
    customer_acquisition_cost: float # CAC
    avg_revenue_per_user: float   # ARPU (客单价)
    variable_cost_per_unit: float # VC (单位变动成本)
    fixed_cost_monthly: float     # 每月固定成本 (租金、底薪等)
    churn_rate_monthly: float     # 月流失率 (0.0 - 1.0)
    days_inventory: int           # DIO (库存天数)
    days_sales_outstanding: int   # DSO (应收天数)
    days_payable: int             # DPO (应付天数)

class FinancialSimulator:
    def __init__(self, assumptions: FinancialAssumptions):
        self.a = assumptions

    def calculate_base_metrics(self) -> Dict:
        """计算基准模型的硬核财务指标"""
        # 1. 贡献毛利 (Contribution Margin)
        contribution_margin = self.a.avg_revenue_per_user - self.a.variable_cost_per_unit
        
        # 2. 盈亏平衡点 (Break-even Volume)
        break_even_vol = self.a.fixed_cost_monthly / contribution_margin if contribution_margin > 0 else float('inf')
        
        # 3. 客户终身价值 (LTV) - 简化版公式: 毛利 / 流失率
        ltv = contribution_margin / self.a.churn_rate_monthly if self.a.churn_rate_monthly > 0 else 0
        
        # 4. 回本周期 (Payback Period)
        payback_months = self.a.customer_acquisition_cost / contribution_margin if contribution_margin > 0 else float('inf')
        
        # 5. 现金转换周期 (CCC)
        ccc = self.a.days_inventory + self.a.days_sales_outstanding - self.a.days_payable
        
        # 6. 资金跑道 (Cash Runway) - 假设初期获客且未盈亏平衡时的烧钱速度
        monthly_burn = self.a.fixed_cost_monthly + (self.a.customer_acquisition_cost * 100) # 假设每月拉新100人
        runway = self.a.initial_capital / monthly_burn if monthly_burn > 0 else 0

        return {
            "contribution_margin": round(contribution_margin, 2),
            "break_even_volume": round(break_even_vol, 0),
            "ltv": round(ltv, 2),
            "ltv_cac_ratio": round(ltv / self.a.customer_acquisition_cost, 2) if self.a.customer_acquisition_cost > 0 else 0,
            "payback_months": round(payback_months, 1),
            "cash_conversion_cycle_days": ccc,
            "monthly_burn_rate": round(monthly_burn, 2),
            "runway_months": round(runway, 1)
        }

    def generate_stress_scenarios(self) -> Dict:
        """生成多场景生存测试 (通过改变参数并重新调用计算)"""
        # 悲观情景：CAC涨30%，流失率涨50%
        downside_assumptions = self.a.model_copy()
        downside_assumptions.customer_acquisition_cost *= 1.30
        downside_assumptions.churn_rate_monthly *= 1.50
        downside_simulator = FinancialSimulator(downside_assumptions)
        
        # 极端压力：毛利下降，回款延期
        severe_assumptions = self.a.model_copy()
        severe_assumptions.variable_cost_per_unit *= 1.20 # 成本上涨
        severe_assumptions.days_sales_outstanding += 30   # 回款拖延一个月
        severe_simulator = FinancialSimulator(severe_assumptions)

        return {
            "base_scenario": self.calculate_base_metrics(),
            "downside_scenario": downside_simulator.calculate_base_metrics(),
            "severe_stress_scenario": severe_simulator.calculate_base_metrics()
        }