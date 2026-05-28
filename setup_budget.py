"""
=============================================================
  AttritionIQ — AWS Budget Alert Setup
  Creates a monthly budget with email + SNS notifications
  so you never get a surprise AWS bill.

  Usage: python setup_budget.py --email your@email.com --limit 20
=============================================================
"""

import boto3
import os
import json
import argparse
from dotenv import load_dotenv

load_dotenv()

REGION     = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
BUDGET_NAME = "AttritionIQ-Monthly-Budget"


def get_account_id():
    sts = boto3.client("sts", region_name=REGION)
    return sts.get_caller_identity()["Account"]


def setup_budget(email: str, limit_usd: float):
    account_id = get_account_id()
    budgets    = boto3.client("budgets", region_name="us-east-1")  # budgets is global

    print(f"  Account ID  : {account_id}")
    print(f"  Budget limit: ${limit_usd:.2f} / month")
    print(f"  Alert email : {email}")

    budget = {
        "BudgetName":   BUDGET_NAME,
        "BudgetLimit":  {"Amount": str(limit_usd), "Unit": "USD"},
        "TimeUnit":     "MONTHLY",
        "BudgetType":   "COST",
        "CostFilters":  {},
        "CostTypes": {
            "IncludeTax":             True,
            "IncludeSubscription":    True,
            "UseBlended":             False,
            "IncludeRefund":          False,
            "IncludeCredit":          False,
            "IncludeUpfront":         True,
            "IncludeRecurring":       True,
            "IncludeOtherSubscription": True,
            "IncludeSupport":         True,
            "IncludeDiscount":        True,
            "UseAmortized":           False,
        },
    }

    # Notify at 80% and 100% of budget
    notifications = [
        {
            "Notification": {
                "NotificationType":   "ACTUAL",
                "ComparisonOperator": "GREATER_THAN",
                "Threshold":          80.0,
                "ThresholdType":      "PERCENTAGE",
            },
            "Subscribers": [
                {"SubscriptionType": "EMAIL", "Address": email}
            ],
        },
        {
            "Notification": {
                "NotificationType":   "ACTUAL",
                "ComparisonOperator": "GREATER_THAN",
                "Threshold":          100.0,
                "ThresholdType":      "PERCENTAGE",
            },
            "Subscribers": [
                {"SubscriptionType": "EMAIL", "Address": email}
            ],
        },
        {
            "Notification": {
                "NotificationType":   "FORECASTED",
                "ComparisonOperator": "GREATER_THAN",
                "Threshold":          100.0,
                "ThresholdType":      "PERCENTAGE",
            },
            "Subscribers": [
                {"SubscriptionType": "EMAIL", "Address": email}
            ],
        },
    ]

    try:
        budgets.create_budget(
            AccountId=account_id,
            Budget=budget,
            NotificationsWithSubscribers=notifications,
        )
        print(f"\n  -> Budget created: {BUDGET_NAME}")
        print(f"  -> You'll be emailed at 80% (${limit_usd * 0.8:.2f}) "
              f"and 100% (${limit_usd:.2f}) of your monthly spend.")

    except budgets.exceptions.DuplicateRecordException:
        # Update existing budget
        budgets.update_budget(
            AccountId=account_id,
            NewBudget=budget,
        )
        print(f"\n  -> Budget updated: {BUDGET_NAME} (${limit_usd}/month)")

    except Exception as e:
        print(f"\n  ! Error: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True,
                        help="Email to receive budget alerts")
    parser.add_argument("--limit", type=float, default=20.0,
                        help="Monthly budget limit in USD (default: $20)")
    args = parser.parse_args()

    print("=" * 60)
    print("  AttritionIQ — AWS Budget Setup")
    print("=" * 60)
    setup_budget(args.email, args.limit)
    print("\n[DONE] Budget alert configured!")
