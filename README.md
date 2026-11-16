# Hướng dẫn FireWatch IoT

Mô hình báo cháy gồm ESP32 (cảm biến lửa, gas MQ-2, quạt, bơm, còi, servo), broker Mosquitto, backend Spring Boot lưu dữ liệu trên PostgreSQL (Supabase) và dashboard web. Đây là **mô hình học tập**, không phải hệ thống báo cháy được chứng nhận và không thay thế thiết bị PCCC.

```
ESP32 ──MQTT──> Mosquitto (laptop) ──> Backend Spring Boot ──> PostgreSQL (Supabase)
                                              │
                                  Dashboard web (frontend/)
```

## 1. Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| `esp32_mqtt/` | Firmware ESP32 (`esp32_mqtt.ino`, `types.h`). Mỗi máy tự tạo `config.h` |
| `mosquitto/` | Cấu hình broker (`firewatch.conf`) và quyền topic mẫu (`aclfile.example`) |
| `backend/` | Spring Boot: REST API, đăng nhập/phân quyền, nhận MQTT, lưu DB |
| `frontend/` | Dashboard HTML/CSS/JS, do backend phục vụ |

## 2. Cài đặt cần có

| Phần mềm | Dùng cho | Kiểm tra |
|---|---|---|
| JDK 21 trở lên | Chạy backend | `java -version` |
| Maven 3.9+ (hoặc IntelliJ IDEA) | Build/chạy backend | `mvn -v` |
| Mosquitto 2.x | Broker MQTT, tải tại [mosquitto.org/download](https://mosquitto.org/download/) | Xem Bước 4 |
| Arduino IDE 2 | Nạp firmware ESP32 | – |
| Tài khoản Supabase | Database PostgreSQL | – |

## 3. Tải dự án

```powershell
git clone <URL_REPOSITORY_GITHUB>
cd BTL_IOT
```

Mọi lệnh Mosquitto bên dưới phải chạy ở **thư mục gốc dự án** (nơi có thư mục `mosquitto`). Kiểm tra:

```powershell
Test-Path .\mosquitto\firewatch.conf
```

Kết quả phải là `True`. Nếu `False`, `cd` vào đúng thư mục dự án.

## 4. Tạo database trên Supabase

Làm **một lần** cho cả nhóm, do người quản lý database thực hiện.

1. Tạo project trên Supabase.
2. Vào phần cài đặt **Data API** của project, tắt **Enable Data API**. Backend kết nối thẳng PostgreSQL nên không cần API này; tắt đi để bảng không bị lộ qua API công khai.
3. Vào **SQL Editor**, mở `backend/schema.sql`, copy toàn bộ rồi bấm **Run**.
4. Kiểm tra trong **Table Editor**, chọn schema `app`: phải có 5 bảng `users`, `devices`, `alarm_events`, `audit_logs`, `user_devices`.
5. Lấy thông tin kết nối: **Connect → Session pooler** (cổng **5432**). Không dùng Transaction pooler cổng 6543.

Người quản lý database gửi riêng thông tin kết nối cho từng thành viên. **Không gửi mật khẩu DB vào group chat hay commit lên GitHub.**

## 5. Tạo tài khoản Mosquitto

Mở **PowerShell bằng Run as Administrator**, chuyển về thư mục gốc dự án:

```powershell
Test-Path "$env:ProgramFiles\mosquitto\mosquitto_passwd.exe"
New-Item -ItemType Directory -Force "C:\ProgramData\MosquittoFireWatch"
Copy-Item .\mosquitto\aclfile.example "C:\ProgramData\MosquittoFireWatch\aclfile" -Force
```

Nếu lệnh đầu trả về `False`, cài Mosquitto rồi mở PowerShell mới.

Tạo hai tài khoản, mỗi lệnh hỏi mật khẩu **2 lần**. Mật khẩu do bạn **tự đặt**; ký tự gõ vào không hiện:

```powershell
& "$env:ProgramFiles\mosquitto\mosquitto_passwd.exe" -c "C:\ProgramData\MosquittoFireWatch\passwd" esp32-device
& "$env:ProgramFiles\mosquitto\mosquitto_passwd.exe" "C:\ProgramData\MosquittoFireWatch\passwd" firewatch-server
```

| Tài khoản | Mật khẩu dùng ở |
|---|---|
| `esp32-device` | `esp32_mqtt/config.h` (Bước 8) |
| `firewatch-server` | `MQTT_PASS` trong `backend/.env` (Bước 9) |

⚠️ Chỉ lệnh **đầu tiên** có `-c`. Chạy lại lệnh có `-c` sẽ xóa các tài khoản đã tạo. Quên mật khẩu thì chạy lại lệnh **không có `-c`** cho tài khoản đó để đặt mật khẩu mới.

## 6. Khởi động Mosquitto

Nếu dịch vụ Mosquitto của Windows đang chạy, nó sẽ chiếm cổng 1883. Dừng nó (PowerShell Administrator):

```powershell
Get-Service *mosquitto*
Stop-Service mosquitto
```

Mở **PowerShell thường** ở thư mục gốc dự án và chạy:

```powershell
& "$env:ProgramFiles\mosquitto\mosquitto.exe" -c "$PWD\mosquitto\firewatch.conf" -v
```

Thấy `Opening ipv4 listen socket on port 1883` là broker đã chạy. **Giữ cửa sổ này mở.**

MQTT cổng 1883 không mã hóa. Chỉ dùng trong Wi-Fi/LAN tin cậy, không mở cổng 1883 ra Internet.

## 7. Lấy địa chỉ IP laptop

```powershell
ipconfig
```

Tìm `IPv4 Address` của adapter Wi-Fi, ví dụ `192.168.0.103`. ESP32 và điện thoại phải dùng cùng mạng Wi-Fi với laptop; mạng Guest có thể chặn các thiết bị liên lạc với nhau.

## 8. Nạp firmware ESP32

Tạo file `esp32_mqtt/config.h` với nội dung sau, thay bằng giá trị thật:

```cpp
const char WIFI_SSID[] = "TEN_WIFI_2_4GHZ";
const char WIFI_PASS[] = "MAT_KHAU_WIFI";
const char MQTT_HOST[] = "192.168.0.103";   // IPv4 laptop ở Bước 7
const int  MQTT_PORT = 1883;
const bool MQTT_TLS = false;
const char MQTT_USER[] = "esp32-device";
const char MQTT_PASS[] = "MAT_KHAU_ESP32";  // mật khẩu esp32-device ở Bước 5
const char DEVICE_ID[] = "esp32-tang1";     // phải trùng device_id trong bảng devices
const char MQTT_ROOT_CA[] = "";             // để trống khi MQTT_TLS = false
```

`config.h` chứa mật khẩu Wi-Fi/MQTT và đã nằm trong `.gitignore`; không commit file này.

Trong Arduino IDE:

1. **Boards Manager:** cài **esp32 by Espressif Systems**, chọn board **ESP32 Dev Module**.
2. **Library Manager:** cài `PubSubClient`, `ESP32Servo`, `Adafruit GFX Library`, `Adafruit SSD1306` (chọn **Install all** khi được hỏi thư viện phụ thuộc).
3. Mở `esp32_mqtt/esp32_mqtt.ino`, chọn đúng cổng COM, bấm **Verify** rồi **Upload**.
4. Mở **Serial Monitor** ở baud `115200`. Phải thấy dòng `MQTT CONNECTED (LAN plain)`.

## 9. Cấu hình backend

Trong thư mục `backend`, copy file mẫu:

```powershell
cd backend
Copy-Item .env.example .env
notepad .env
```

Điền các giá trị:

```properties
DB_URL=jdbc:postgresql://<SESSION_POOLER_HOST>:5432/postgres?sslmode=require&currentSchema=app
DB_USER=postgres.<PROJECT_REF>
DB_PASS=<mật khẩu database>

MQTT_URL=tcp://127.0.0.1:1883
MQTT_USER=firewatch-server
MQTT_PASS=<mật khẩu firewatch-server ở Bước 5>

ADMIN_USER=admin
ADMIN_PASS=<mật khẩu Admin, ít nhất 10 ký tự>

WEB_PORT=8080
```

Lưu ý:
- `.env` phải nằm **trong thư mục `backend/`**, không phải thư mục gốc.
- `DB_URL` phải bắt đầu bằng `jdbc:postgresql://`. Không dán nguyên chuỗi `postgresql://user:pass@...` mà Supabase hiển thị; user và mật khẩu điền riêng vào `DB_USER`, `DB_PASS`.
- Không bọc giá trị trong dấu nháy.
- `ADMIN_PASS` chỉ dùng để tạo Admin đầu tiên khi bảng `users` còn trống. Tạo xong nên xóa giá trị này.

## 10. Chạy backend

Mở PowerShell mới (cửa sổ Mosquitto vẫn chạy):

```powershell
cd backend
mvn spring-boot:run
```

Lần đầu Maven tải thư viện mất vài phút. Chạy thành công khi log có:

```
Started App in ... seconds
>>> Da tao Admin: admin ...        (chỉ lần đầu)
MQTT da ket noi: tcp://127.0.0.1:1883
```

Mở `http://127.0.0.1:8080` và đăng nhập bằng `ADMIN_USER` / `ADMIN_PASS`.

- Luôn chạy lệnh từ **trong thư mục `backend`**; backend đọc `.env` và `../frontend` theo thư mục đang đứng.
- Chạy bằng IntelliJ: mở thư mục `backend`, chạy `App.java`, đặt *Working directory* là thư mục `backend`.
- Chỉ chạy **một** backend cho cùng broker, nếu không sự kiện có thể bị xử lý trùng.
- Dừng backend bằng `Ctrl + C`.

## 11. Quản lý người dùng và thiết bị

**Người dùng:** Admin vào menu **Người dùng → Thêm người dùng** trên dashboard, tick các quyền *Xem cảm biến và phần cứng*, *Xem ngưỡng cảnh báo*, *Xem lịch sử hoạt động*. Người dùng mới phải đổi mật khẩu tạm ở lần đăng nhập đầu.

**Gán thiết bị:** người dùng thường chỉ thấy các thiết bị được gán (Admin thấy tất cả). Dashboard chưa có giao diện gán, nên tạm thời chạy SQL trong Supabase:

```sql
insert into app.user_devices (user_id, device_id)
select id, 'esp32-tang1' from app.users where username = 'ten_dang_nhap';
```

**Vòng đời thiết bị:** `PENDING → ACTIVE ⇄ DISABLED → RETIRED`. Backend chỉ nhận dữ liệu MQTT từ thiết bị đang `ACTIVE`. Thiết bị không bị xóa mà chuyển sang `RETIRED` để giữ lịch sử.

Thêm một ESP32 mới:
1. Đăng ký thiết bị bằng API Admin (`POST /api/admin/devices`, rồi `PATCH /api/admin/devices/{id}` với `{"status":"ACTIVE"}`), hoặc bằng SQL:
   ```sql
   insert into app.devices (device_id, name, location, status)
   values ('esp32-tang2', 'ESP32 tầng 2', 'Phòng 201', 'ACTIVE');
   ```
2. Thêm tài khoản Mosquitto và quyền topic `fire-demo/esp32-tang2/...` cho thiết bị đó trong `C:\ProgramData\MosquittoFireWatch\aclfile`, rồi khởi động lại broker.
3. Đặt `DEVICE_ID` trong `config.h` của ESP32 mới cho trùng.

**API cho frontend:**

| API | Quyền | Chức năng |
|---|---|---|
| `GET /api/session`, `POST /api/login`, `POST /api/logout`, `POST /api/password` | – | Phiên đăng nhập, đổi mật khẩu |
| `GET /api/device/status?device=` | `view_status` | Trạng thái thiết bị |
| `GET /api/device/thresholds?device=` | `view_thresholds` | Ngưỡng do ESP32 gửi |
| `GET /api/history?device=&before=` | `view_history` | 100 cảnh báo gần nhất |
| `/api/admin/users`, `/api/admin/users/{id}`, `.../reset-password`, `.../devices` | Admin | Quản lý người dùng, gán thiết bị |
| `/api/admin/devices`, `/api/admin/devices/{id}` | Admin | Đăng ký và đổi trạng thái thiết bị |
| `GET /api/admin/audit` | Admin | Nhật ký quản trị |

Mọi request ghi dữ liệu (POST/PATCH/PUT/DELETE) phải gửi header `X-CSRF-Token`, lấy giá trị từ `GET /api/session`.

## 12. Mở dashboard trên điện thoại

1. Điện thoại và laptop dùng cùng Wi-Fi.
2. Mở `http://<IP_LAPTOP>:8080`, ví dụ `http://192.168.0.103:8080`. Không dùng `localhost` trên điện thoại.
3. Nếu không vào được, đặt Wi-Fi là **Private network** trên Windows, rồi mở cổng (PowerShell Administrator):

```powershell
New-NetFirewallRule -DisplayName "FireWatch LAN 8080" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -Profile Private -RemoteAddress LocalSubnet
New-NetFirewallRule -DisplayName "Mosquitto FireWatch LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 1883 -Profile Private -RemoteAddress LocalSubnet
```

Không mở các cổng này trên Public network và không chuyển tiếp cổng trên router. HTTP nội bộ không mã hóa mật khẩu đăng nhập.

## 13. Kiểm tra theo thứ tự

1. **Broker:** cửa sổ Mosquitto có dòng lắng nghe cổng 1883.
2. **Backend:** log có `Started App` và `MQTT da ket noi`.
3. **ESP32:** Serial Monitor báo `MQTT CONNECTED (LAN plain)`.
4. **Dashboard:** đăng nhập được tại `http://127.0.0.1:8080`, trang Tổng quan cập nhật mỗi 2 giây.
5. **Cảnh báo:** kích hoạt cảm biến theo cách an toàn, kiểm tra trang **Lịch sử hoạt động** có sự kiện mới.

Quạt/bơm/còi hiển thị bật là lệnh đầu ra của ESP32, không chứng minh thiết bị vật lý đã chạy. Ngưỡng ADC của MQ-2 chỉ là số thử nghiệm, không phải ppm.

## 14. Xử lý lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| `'url' must start with "jdbc"` | `.env` không nằm trong `backend/`, hoặc `DB_URL` sai định dạng (xem Bước 9) |
| `Schema-validation: missing table` | Sai `currentSchema` (phải là `app`) hoặc chưa chạy `schema.sql` |
| `password authentication failed` | Sai `DB_USER`/`DB_PASS`; `DB_USER` có dạng `postgres.<ref>` |
| `MQTT chua ket noi duoc` lặp lại | Mosquitto chưa chạy, hoặc sai `MQTT_PASS` của `firewatch-server` |
| `Bo qua du lieu tu thiet bi chua kich hoat` | Thiết bị chưa có trong bảng `devices` hoặc không ở trạng thái `ACTIVE` |
| Người dùng đăng nhập được nhưng báo chưa có thiết bị | Chưa gán thiết bị trong `user_devices` (Bước 11) |
| `Port 8080 was already in use` | Có backend khác đang chạy; tắt nó hoặc đổi `WEB_PORT` |
| `Unable to open config file` (Mosquitto) | Đang đứng sai thư mục; `cd` về thư mục gốc dự án |
| `Address already in use` (Mosquitto) | Dịch vụ Mosquitto khác chiếm cổng 1883; chạy `Stop-Service mosquitto` |
| ESP32 `MQTT loi=-2` | Sai IP laptop, khác Wi-Fi, Firewall chặn cổng 1883, hoặc sai mật khẩu `esp32-device` |

## 15. File cần giữ và file không được commit

**Commit lên GitHub:** `esp32_mqtt/*.ino`, `types.h`, `mosquitto/*`, toàn bộ `backend/` (trừ `.env`, `target/`), `frontend/`, `README.md`.

**Không commit** (đã có trong `.gitignore`):

| File | Lý do |
|---|---|
| `backend/.env` | Mật khẩu database, MQTT, Admin |
| `esp32_mqtt/config.h` | Mật khẩu Wi-Fi, MQTT |
| `backend/target/` | File build, Maven tự tạo lại |

Mỗi thành viên tự tạo `backend/.env` từ `backend/.env.example`. Khi thêm biến mới vào `.env`, nhớ thêm tên biến (để trống giá trị) vào `.env.example`. Trước khi commit, chạy `git status` để chắc chắn không có `.env`.

## 16. Giới hạn an toàn

Mô hình dùng Wi-Fi, laptop, cảm biến phổ thông và thiết bị đóng cắt thử nghiệm. Mất điện, mất Wi-Fi, lỗi cảm biến, sai ngưỡng, relay/MOSFET hỏng hoặc cơ cấu bị kẹt đều có thể làm cảnh báo/điều khiển không như mong muốn. Không dùng nó làm hệ thống báo cháy cho nhà cao tầng, không dùng quạt thường trong môi trường khí dễ cháy và không phụ thuộc servo để mở lối thoát hiểm. Công trình thật cần thiết kế, thiết bị, nguồn dự phòng, kiểm định và lắp đặt theo quy chuẩn PCCC bởi đơn vị chuyên môn.
