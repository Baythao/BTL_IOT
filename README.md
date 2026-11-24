# HỆ THỐNG CẢNH BÁO CHÁY, RÒ RỈ KHÍ GAS
## Thành viên nhóm

| STT | Họ và tên        | Mã sinh viên |
|:---:|------------------|:------------:|
| 1   | Thào A Bảy       | B22DCCN072   |
| 2   | Trịnh Quang Anh  | B23DCCN055   |
| 3   | Hoàng Khải Hưng  | B23DCCN365   |

## Hướng dẫn FireWatch IoT tổng hợp

Tài liệu này gộp hướng dẫn cài dashboard web, Mosquitto, ESP32 và bộ nhận cảnh báo. Làm lần lượt theo các bước dưới đây. 

## 1. Tải và mở thư mục dự án

Tải ZIP từ GitHub rồi giải nén toàn bộ, hoặc clone repository:

```powershell
git clone <URL_REPOSITORY_GITHUB>
cd firewatch_mqtt
```

Thay `<URL_REPOSITORY_GITHUB>` bằng địa chỉ repo thật. Nếu đã tải ZIP, mở PowerShell tại thư mục `firewatch_mqtt` vừa giải nén.

**Lưu ý về thư mục hiện hành:** lệnh Mosquitto dùng `$PWD\mosquitto\firewatch.conf`, vì vậy trước khi chạy phải đang đứng ở thư mục gốc `firewatch_mqtt`. Nếu PowerShell đang ở `C:\Users\ADMIN`, đường dẫn sẽ trỏ sai và báo không mở được config. Kiểm tra:

```powershell
Get-Location
Test-Path .\mosquitto\firewatch.conf
```

Lệnh thứ hai phải trả về `True`. Nếu là `False`, `cd` vào đúng thư mục dự án, ví dụ:

```powershell
cd "$HOME\Downloads\ESP32_MQTT_Phone_SMS (1)\firewatch_mqtt"
```

Tên thư mục trên chỉ là ví dụ; dùng đường dẫn thực tế trên máy bạn.

## 2. Cài Python và khởi tạo tài khoản quản trị

Mở PowerShell trong thư mục dự án rồi vào `server`:

```powershell
cd .\server
py -0p
```

Lệnh `py -0p` liệt kê các bản Python đã cài. Nên dùng Python 3.11 hoặc 3.12. Tạo môi trường ảo và cài thư viện:

```powershell
py -3.11 -m venv .venv
```

Nếu máy chỉ có Python 3.12, thay `-3.11` bằng `-3.12`.

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_web.py
.\.venv\Scripts\python.exe web_app.py --init-admin
```

Nhập tên đăng nhập, họ tên và mật khẩu quản trị dài 10–128 ký tự. Khi nhập mật khẩu, PowerShell không hiển thị ký tự; cứ gõ rồi nhấn Enter. Không có mật khẩu mặc định. `setup_web.py` tạo `server\.env` và khóa `WEB_SECRET` nếu chưa có; không gửi/chia sẻ `.env`.

## 3. Tạo tài khoản cho Mosquitto

Mở **PowerShell bằng Run as Administrator**. Chuyển về thư mục gốc dự án, ví dụ:

```powershell
cd "$HOME\Downloads\ESP32_MQTT_Phone_SMS (1)\firewatch_mqtt"
Test-Path .\mosquitto\aclfile.example
```

Nếu kết quả là `True`, tạo thư mục dữ liệu và sao chép ACL mẫu:

```powershell
New-Item -ItemType Directory -Force "C:\ProgramData\MosquittoFireWatch"
Copy-Item .\mosquitto\aclfile.example "C:\ProgramData\MosquittoFireWatch\aclfile" -Force
```

Tạo hai tài khoản riêng: một cho ESP32, một cho chương trình Python. Gõ mật khẩu khi được nhắc; ký tự sẽ không hiện.

```powershell
& "$env:ProgramFiles\mosquitto\mosquitto_passwd.exe" -c "C:\ProgramData\MosquittoFireWatch\passwd" esp32-device
& "$env:ProgramFiles\mosquitto\mosquitto_passwd.exe" "C:\ProgramData\MosquittoFireWatch\passwd" firewatch-server
```

Ở lệnh đầu có `-c` để tạo file mật khẩu mới. Lệnh thứ hai không có `-c`, để giữ tài khoản ESP32 vừa tạo. Ghi nhớ hai mật khẩu; chúng không phải mật khẩu đăng nhập dashboard. ACL giới hạn quyền theo các topic của mô hình.

Kiểm tra Mosquitto đã cài:

```powershell
Test-Path "$env:ProgramFiles\mosquitto\mosquitto.exe"
Test-Path "$env:ProgramFiles\mosquitto\mosquitto_passwd.exe"
```

Cả hai nên trả về `True`. Nếu `False`, cài Mosquitto Broker for Windows từ [mosquitto.org/download](https://mosquitto.org/download/), rồi mở PowerShell mới.

## 4. Khởi động Mosquitto broker

Kiểm tra dịch vụ Mosquitto:

```powershell
Get-Service *mosquitto*
```

Nếu dịch vụ Windows đang chiếm cổng 1883, mở PowerShell Administrator và dừng dịch vụ:

```powershell
Stop-Service mosquitto
```

Nếu không có dịch vụ hoặc dịch vụ đã dừng, bỏ qua lệnh trên. Mở PowerShell thường, chuyển về **thư mục gốc dự án** rồi xác nhận file cấu hình tồn tại:

```powershell
cd "$HOME\Downloads\ESP32_MQTT_Phone_SMS (1)\firewatch_mqtt"
Test-Path .\mosquitto\firewatch.conf
```

Khi kết quả là `True`, chạy broker:

```powershell
& "$env:ProgramFiles\mosquitto\mosquitto.exe" -c "$PWD\mosquitto\firewatch.conf" -v
```

Giữ cửa sổ này mở. Dòng `Opening ipv4 listen socket on port 1883` cho biết broker đang lắng nghe. Dòng `mosquitto ... running` cho biết tiến trình đã chạy.

Nếu thấy `Unable to open config file`, PowerShell đang sai thư mục hoặc đường dẫn cấu hình sai. Chạy `Get-Location` và `Test-Path .\mosquitto\firewatch.conf`; chuyển về thư mục gốc dự án rồi thử lại.

Nếu thấy `Address already in use`, một tiến trình khác đang dùng cổng 1883. Kiểm tra:

```powershell
Get-NetTCPConnection -LocalPort 1883 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

Xem tiến trình bằng `Get-Process -Id <OwningProcess>`. Chỉ dừng tiến trình Mosquitto cũ nếu bạn xác nhận đó là broker đang chạy trùng; không dừng tiến trình lạ.

MQTT 1883 trong cấu hình này không mã hóa TLS. Chỉ dùng trên Wi-Fi/LAN đáng tin cậy; không mở cổng 1883 ra Internet và không cấu hình port forwarding trên router.

## 5. Lấy địa chỉ IP laptop

Mở một PowerShell mới:

```powershell
ipconfig
```

Tìm `IPv4 Address` trong adapter Wi-Fi đang kết nối, ví dụ `192.168.0.103`. Dùng đúng địa chỉ hiện tại thay cho địa chỉ ví dụ trong các bước sau. ESP32 và điện thoại cần ở cùng mạng Wi-Fi; mạng Guest có thể chặn các thiết bị liên lạc với nhau.

## 6. Tạo cấu hình, cài thư viện và nạp firmware ESP32

Từ thư mục gốc `firewatch_mqtt`, tạo bản cấu hình riêng trong `esp32_mqtt` từ mẫu:

```powershell
Copy-Item .\esp32_mqtt\config.example.h .\esp32_mqtt\config.h
```

Mở `esp32_mqtt\config.h` bằng Arduino IDE hoặc Notepad. Điền tên/mật khẩu Wi-Fi 2.4 GHz, IPv4 laptop và mật khẩu tài khoản `esp32-device`:

```cpp
const char WIFI_SSID[] = "TEN_WIFI_2_4GHZ";
const char WIFI_PASS[] = "MAT_KHAU_WIFI";
const char MQTT_HOST[] = "192.168.0.103"; // IPv4 laptop, thay bằng IP thật
const int MQTT_PORT = 1883;
const bool MQTT_TLS = false;
const char MQTT_USER[] = "esp32-device";
const char MQTT_PASS[] = "MAT_KHAU_ESP32";
const char DEVICE_ID[] = "esp32-tang1";
```

Giữ `DEVICE_ID` bằng `esp32-tang1` trừ khi bạn chủ động đổi đồng nhất trong ACL, `.env` và firmware. Với Mosquitto nội bộ, không cần điền CA; không chép mật khẩu thật vào tài liệu hoặc GitHub.

Mở `esp32_mqtt\esp32_mqtt.ino` trong Arduino IDE. Đảm bảo `config.h` và `types.h` nằm cùng thư mục với file `.ino`.

### Cài hỗ trợ bo mạch ESP32 nếu chưa có

1. Kết nối Internet và mở Arduino IDE.
2. Mở **Tools → Board → Boards Manager** (hoặc biểu tượng Boards Manager ở thanh bên).
3. Tìm `esp32`, chọn gói **esp32 by Espressif Systems**, nhấn **Install** và chờ hoàn tất.
4. Chọn **Tools → Board → ESP32 Arduino → ESP32 Dev Module**. Tên mục có thể hiển thị khác nhẹ tùy phiên bản Arduino IDE.

### Cài bốn thư viện cần cho firmware

1. Mở **Sketch → Include Library → Manage Libraries…**. Trong Arduino IDE 2, có thể mở biểu tượng **Library Manager** ở thanh bên.
2. Chờ danh sách thư viện tải xong, nhập từng tên vào ô tìm kiếm và nhấn **Install**:
   - `PubSubClient` — MQTT client cho ESP32.
   - `ESP32Servo` — điều khiển servo.
   - `Adafruit GFX Library` — thư viện đồ họa dùng chung của Adafruit.
   - `Adafruit SSD1306` — điều khiển màn OLED SSD1306.
3. Khi IDE hỏi cài các thư viện phụ thuộc, chọn **Install all**. Nếu Adafruit SSD1306 yêu cầu `Adafruit BusIO`, cũng cài thư viện đó.
4. Chờ trạng thái mỗi thư viện chuyển sang **Installed**. Không cần cài riêng `WiFi` hoặc `Wire`; chúng có sẵn trong gói hỗ trợ ESP32.

Sau khi cài xong, đóng Library Manager. Nếu trước đó IDE báo `PubSubClient.h`, `ESP32Servo.h`, `Adafruit_GFX.h` hoặc `Adafruit_SSD1306.h: No such file or directory`, đóng rồi mở lại Arduino IDE để IDE quét lại thư viện; kiểm tra các gói trên hiển thị **Installed**, sau đó Verify lại.

Chọn đúng board **ESP32 Dev Module** (ESP32 DevKit V1 cổ điển) và đúng cổng COM trong **Tools → Port**. Nhấn **Verify** trước; khi biên dịch thành công, nhấn **Upload**. Mở **Tools → Serial Monitor**, đặt baud `115200`. Khi dùng Mosquitto LAN, cần thấy `MQTT CONNECTED (LAN plain)`. Nếu firmware có màn OLED, trạng thái MQTT cũng cần báo ON.

`config.h` chứa thông tin riêng, không commit file đó lên GitHub. Chỉ commit mẫu `config.example.h`.

## 7. Cấu hình Python kết nối MQTT

Mở PowerShell mới và vào `server` trong dự án:

```powershell
cd "$HOME\Downloads\ESP32_MQTT_Phone_SMS (1)\firewatch_mqtt\server"
notepad .env
```

Không tạo `.env` bằng cách ghi đè nếu `setup_web.py` đã tạo file; phải giữ nguyên `WEB_SECRET`. Điền hoặc sửa các giá trị sau, dùng mật khẩu tài khoản `firewatch-server`:

```ini
MQTT_HOST=192.168.0.103
MQTT_PORT=1883
MQTT_TLS=0
MQTT_USER=firewatch-server
MQTT_PASS=MAT_KHAU_SERVER
DEVICE_ID=esp32-tang1
MQTT_CA_FILE=
DRY_RUN=1
PUSH_ENABLED=0
SMS_ENABLED=0
SITE_NAME=Mo hinh tang 1
WEB_HOST=0.0.0.0
WEB_PORT=5000
WEB_HTTPS=0
```

Thay IP và mật khẩu bằng giá trị thật trên máy. Giữ các dòng `WEB_SECRET` khác mà `setup_web.py` đã tạo. `DRY_RUN=1`, `PUSH_ENABLED=0`, `SMS_ENABLED=0` giúp chạy thử mà không gửi thông báo thật hoặc phát sinh phí. File `.env` không được đưa lên GitHub.

## 8. Khởi động web và MQTT collector

Để dễ theo dõi, mở **ba cửa sổ PowerShell** và để cả ba chạy. Không đóng cửa sổ khi đang dùng hệ thống.

**Cửa sổ 1 — Mosquitto:** đang chạy lệnh ở Bước 4, thư mục gốc `firewatch_mqtt`.
```powershell
& "$env:ProgramFiles\mosquitto\mosquitto.exe" -c "$PWD\mosquitto\firewatch.conf" -v
```
**Cửa sổ 2 — web dashboard:**

```powershell
cd server
.\.venv\Scripts\python.exe web_app.py
```

Giữ cửa sổ mở. Trên laptop, mở `http://127.0.0.1:5000` và đăng nhập bằng tài khoản Admin đã tạo ở Bước 2.

**Cửa sổ 3 — MQTT collector:**

```powershell
cd server
.\.venv\Scripts\python.exe notify_server.py
```

Collector cần báo đã kết nối MQTT. Chỉ chạy **một** `notify_server.py` cho cùng database `alerts.sqlite3`; hai collector cùng lúc có thể tranh client ID hoặc xử lý thông báo lặp.

Có thể quản lý người dùng từ dashboard: **Người dùng → Thêm người dùng**, sau đó chọn quyền xem phù hợp. Admin có thể sửa quyền, khóa/mở khóa, đặt lại mật khẩu hoặc xóa tài khoản. Tài khoản người dùng không tự có quyền quản trị.

## 9. Mở dashboard trên điện thoại

1. Laptop vẫn chạy `web_app.py`; điện thoại và laptop cùng Wi-Fi.
2. Dùng IP laptop lấy ở Bước 5, ví dụ mở `http://192.168.0.103:5000` trên điện thoại.
3. Đăng nhập bằng tài khoản riêng do Admin tạo.
4. Không dùng `localhost` hoặc `127.0.0.1` trên điện thoại; các địa chỉ đó trỏ về chính điện thoại.

Nếu điện thoại không vào được, đặt Wi-Fi tin cậy thành **Private network** trên Windows. Chỉ khi Firewall chặn kết nối LAN, mở PowerShell Administrator và thêm quy tắc cho mạng nội bộ riêng:

```powershell
New-NetFirewallRule -DisplayName "FireWatch LAN 5000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5000 -Profile Private -RemoteAddress LocalSubnet
```

Nếu ESP32 không kết nối broker, có thể cần quy tắc tương tự cho TCP 1883 trên Private network:

```powershell
New-NetFirewallRule -DisplayName "Mosquitto FireWatch LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 1883 -Profile Private -RemoteAddress LocalSubnet
```

Không mở các quy tắc này trên Public network, không chuyển tiếp cổng trên router, và không đưa dashboard HTTP ra Internet. HTTP nội bộ không mã hóa thông tin đăng nhập. Truy cập từ xa cần triển khai server/broker có TLS hoặc VPN riêng.

## 10. Cảnh báo Email và PostgreSQL

Phiên bản này gửi email SMTP. Có thể dùng PostgreSQL thật cho cả collector và dashboard. 

## 11. Kiểm tra kết nối theo thứ tự

1. **Broker:** cửa sổ 1 còn chạy và có log lắng nghe cổng 1883.
2. **ESP32:** Serial Monitor 115200 báo Wi-Fi đã kết nối và `MQTT CONNECTED (LAN plain)`.
3. **Collector:** cửa sổ 3 báo MQTT đã kết nối; không báo lỗi xác thực.
4. **Dashboard laptop:** đăng nhập được tại `http://127.0.0.1:5000`.
5. **Dữ liệu:** kích hoạt cảm biến theo cách an toàn; xem Serial, OLED và dashboard cập nhật. Dữ liệu web có thể trễ vài giây.
6. **Điện thoại:** mở bằng `http://IP_LAPTOP:5000` và đăng nhập tài khoản người dùng.
7. **Email:** chạy thử `DRY_RUN=1` rồi chuyển `DRY_RUN=0`; SMTP accepted không bảo đảm đã giao vào Inbox.

Quạt/bơm/còi hiển thị bật là lệnh đầu ra của ESP32, không chứng minh thiết bị vật lý đã chạy. Servo hiển thị 0°/90° là góc lệnh, không phải phản hồi đo vị trí. Ngưỡng ADC của MQ-2 chỉ là số thử nghiệm, không phải ppm và không đảm bảo cảnh báo an toàn.

## 12. Xử lý lỗi thường gặp

| Lỗi/hiện tượng | Kiểm tra và xử lý |
|---|---|
| `Unable to open config file ... C:\Users\ADMIN\mosquitto\firewatch.conf` | Đang chạy ở thư mục `C:\Users\ADMIN`. `cd` về thư mục gốc dự án; `Test-Path .\mosquitto\firewatch.conf` phải là `True`, rồi chạy lại lệnh broker. |
| `Address already in use` | Có Mosquitto khác chiếm cổng 1883. Kiểm tra `Get-NetTCPConnection -LocalPort 1883 -State Listen` và dừng đúng dịch vụ/tiến trình Mosquitto trùng. |
| ESP32 `MQTT loi=-2` hoặc không tới broker | Kiểm tra broker đang chạy, IP laptop mới nhất, cùng Wi-Fi không phải Guest, Firewall Private cho phép 1883, username/password ESP32. |
| ESP32 lỗi xác thực/quyền | Đối chiếu `esp32-device` và mật khẩu trong `config.h`; xác nhận `aclfile` có quyền đúng cho `esp32-tang1`. |
| ESP32 MQTT connected nhưng website chưa có dữ liệu | Chạy `notify_server.py`; đối chiếu `.env` dùng `firewatch-server`, đúng mật khẩu, IP và `DEVICE_ID=esp32-tang1`; firmware phải gửi topic `/state`. |
| Laptop mở web được nhưng iPhone không mở | Dùng IPv4 laptop thay localhost; cùng Wi-Fi; kiểm tra Firewall Private và AP/Guest isolation. |
| Lệnh `python.exe` không tìm thấy | Đang ở sai thư mục. Vào `server`, kiểm tra `Test-Path .\.venv\Scripts\python.exe`; nếu False thì tạo venv và cài requirements theo Bước 2. |
| Cửa sổ PowerShell bị đóng | Tiến trình tương ứng đã dừng; mở cửa sổ mới, vào đúng thư mục và chạy lại lệnh của tiến trình đó. |

## 13. Những file CODE chính

Các file chương trình và mẫu cấu hình sau khi tải dự án:

- `esp32_mqtt/esp32_mqtt.ino`, `esp32_mqtt/types.h`, `esp32_mqtt/config.example.h` — firmware và mẫu cấu hình.
- `mosquitto/firewatch.conf`, `mosquitto/aclfile.example` — broker và quyền topic mẫu.
- Thư mục `server/` gồm `web_app.py`, `notify_server.py`, `device_store.py`, `requirements.txt`, `setup_web.py`, `templates/`, `static/` — ứng dụng máy chủ.
- `README.md` và tài liệu hướng dẫn — tài liệu dự án.

`server/test_web.py` và `server/test_notify_server.py` chỉ phục vụ kiểm thử tự động; không cần để khởi động hệ thống. 

Các file riêng trên mỗi máy như `server/.env`, `esp32_mqtt/config.h`, `server/alerts.sqlite3` không được chia sẻ công khai. `.env` chứa bí mật và cấu hình web; `config.h` chứa Wi-Fi/MQTT.


