# Aldi Talk Integration for Home Assistant

This custom component for Home Assistant allows users to access their Aldi Talk account data directly within Home Assistant, providing a convenient way to monitor account details such as account balance, data volume, and validity periods.

## Disclaimer

This component uses web scraping, not an official Aldi Talk API. It may be subject to errors or changes in Aldi Talk's website structure that could affect functionality.
Use this component at your own risk, understanding potential risks including account issues or violations of Aldi Talk's terms. The developers are not affiliated with Aldi Talk and are not liable for any damages resulting from its use. Your use indicates acceptance of these risks.

## Setup Instructions

1. Ensure you have your [Aldi Talk login credentials](https://login.alditalk-kundenbetreuung.de/sso/UI/Login?service=login) ready.
2. Use these credentials to set up the Aldi Talk integration via Home Assistant's UI.

## Available Sensors

This component provides access to the following sensors within Home Assistant, allowing you to monitor various aspects of your Aldi Talk account:

| Sensor Name           | Description                      | Domain                         |
| --------------------- | -------------------------------- | ------------------------------ |
| Account Balance       | The current account balance.     | `sensor.account_balance`       |
| Start Day             | The start date of the plan.      | `sensor.start_day`             |
| End Day               | The expiration date of the plan. | `sensor.end_day`               |
| Total Data Volume     | Total data volume available.     | `sensor.total_data_volume`     |
| Remaining Data Volume | Data volume remaining.           | `sensor.remaining_data_volume` |

The data will update every 30 minutes.

You can change the unit of measurement via the entity configuration to display it in GB

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/Jonas_JoKu)
