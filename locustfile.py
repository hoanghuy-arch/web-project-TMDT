"""Kịch bản kiểm thử tải (Load Testing) hệ thống SportZone bằng Locust.
Cách chạy:
    locust -f locustfile.py --host=http://localhost:5000
    Hoặc mở giao diện web Locust tại: http://localhost:8089
"""
from locust import HttpUser, task, between
import random


class WebsiteUser(HttpUser):
    # Thời gian chờ giữa các thao tác của người dùng: 1 đến 3 giây
    wait_time = between(1, 3)

    @task(3)
    def view_homepage(self):
        """Khách truy cập trang chủ (tần suất cao)."""
        self.client.get("/")

    @task(4)
    def view_products(self):
        """Khách duyệt danh mục và tìm kiếm sản phẩm."""
        self.client.get("/products")

    @task(2)
    def check_health(self):
        """Kiểm tra phản hồi của endpoint giám sát hệ thống."""
        self.client.get("/health")
