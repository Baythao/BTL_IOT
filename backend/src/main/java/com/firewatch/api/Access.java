package com.firewatch.api;

import com.firewatch.model.Device;
import com.firewatch.model.Repos;
import com.firewatch.model.User;
import jakarta.servlet.http.HttpSession;
import org.springframework.stereotype.Component;

/**
 * Kiem tra dang nhap va phan quyen, dung chung cho moi controller.
 * User duoc nap lai tu DB moi request: bi khoa/xoa/doi quyen co hieu luc ngay.
 */
@Component
public class Access {
    private final Repos.Users users;
    private final Repos.Devices devices;

    public Access(Repos.Users users, Repos.Devices devices) {
        this.users = users;
        this.devices = devices;
    }

    /** User dang dang nhap, hoac null neu chua dang nhap / bi khoa / bi xoa. */
    public User findUser(HttpSession s) {
        Object uid = s.getAttribute("uid");
        if (!(uid instanceof Long)) return null;
        User u = users.findById((Long) uid).orElse(null);
        if (u == null || !u.active) {
            s.removeAttribute("uid");
            return null;
        }
        return u;
    }

    /** Bat buoc dang nhap. allowMustChange = true chi dung cho doi mat khau. */
    public User loggedIn(HttpSession s, boolean allowMustChange) {
        User u = findUser(s);
        if (u == null) throw new ApiError(401, "Vui lòng đăng nhập.");
        if (u.mustChange && !allowMustChange) throw new ApiError(403, "Bạn cần đổi mật khẩu tạm trước khi tiếp tục.");
        return u;
    }

    /** Bat buoc co quyen (view_status, view_thresholds, view_history). */
    public User need(HttpSession s, String permission) {
        User u = loggedIn(s, false);
        if (!u.can(permission)) throw new ApiError(403, "Bạn chưa được cấp quyền cho chức năng này.");
        return u;
    }

    public User admin(HttpSession s) {
        User u = loggedIn(s, false);
        if (!u.isAdmin()) throw new ApiError(403, "Chỉ Admin được thực hiện thao tác này.");
        return u;
    }

    /** Thiet bi mac dinh: thiet bi ACTIVE dau tien ma user duoc xem. */
    public String defaultDevice(User u) {
        for (Device d : devices.findAllByOrderByDeviceId()) {
            if (d.status.equals("ACTIVE") && (u.isAdmin() || u.devices.contains(d.deviceId))) return d.deviceId;
        }
        return null;
    }

    /** Kiem tra user co duoc xem thiet bi nay khong (bang user_devices). */
    public Device allowedDevice(User u, String id) {
        if (id == null || id.isBlank()) id = defaultDevice(u);
        if (id == null) throw new ApiError(404, "Chưa có thiết bị nào được gán cho bạn.");
        if (!u.isAdmin() && !u.devices.contains(id)) throw new ApiError(403, "Bạn không được xem thiết bị này.");
        return devices.findById(id).orElseThrow(() -> new ApiError(404, "Không tìm thấy thiết bị."));
    }
}
