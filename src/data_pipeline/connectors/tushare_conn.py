from base import BaseConnector
# import tushare as ts


class TushareConnector(BaseConnector):
    def __init__(self):
        # self.pro = ts.pro_api(TUSHARE_TOKEN)
        pass

    def fetch(self, start_date: str, end_date: str):
        # return self.pro.daily(start_date=start_date, end_date=end_date)
        pass
