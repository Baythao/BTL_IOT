package com.firewatch.api;

import com.firewatch.model.AuditLog;
import com.firewatch.model.Repos;
import com.firewatch.model.User;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;
import java.util.*;

/** Admin: quan ly nguoi dung, gan thiet bi, xem nhat ky. */
@RestController
@RequestMapping("/api/admin")
public class AdminUserController {
    private final Repos.Users users;
    private final Repos.Devices devices;
    private final Repos.Audits audits;
    private final PasswordEncoder encoder;
    private final Access access;

    public AdminUserController(Repos.Users users, Repos.Devices devices, Repos.Audits audits,
                               PasswordEncoder encoder, Access access) {
        this.users = users;
        this.devices = devices;
        this.audits = audits;
        this.encoder = encoder;
        this.access = access;
    }

    @GetMapping("/users")
    public Map<String, Object> list(HttpSession s) {
        access.admin(s);
        List<Map<String, Object>> list = new ArrayList<>();
        for (User u : users.findAll()) list.add(Json.user(u));
        list.sort(Comparator.comparing(m -> (Long) m.get("id")));
        return Map.of("users", list);
    }

    @PostMapping("/users")
    public ResponseEntity<Map<String, Object>> create(@RequestBody Map<String, Object> b, HttpSession s) {
        User me = access.admin(s);
        User u = new User();
        u.username = Json.text(b, "username", 3, 32).toLowerCase();
        if (!u.username.matches("[a-z0-9_.-]+")) throw new ApiError(400, "Tên đăng nhập: chữ không dấu, số, dấu . _ -");
        if (users.findByUsername(u.username).isPresent()) throw new ApiError(409, "Tên đăng nhập đã tồn tại.");
        u.passwordHash = encoder.encode(Json.text(b, "password", 10, 128));
        u.mustChange = true;                            // user moi phai doi mat khau tam
        applyFields(u, b);
        users.save(u);
        audits.log(me.username, "create_user", u.username);
        return ResponseEntity.status(201).body(Map.of("id", u.id));
    }

    @PatchMapping("/users/{id}")
    public Map<String, Object> update(@PathVariable Long id, @RequestBody Map<String, Object> b, HttpSession s) {
        User me = access.admin(s);
        User u = find(id);
        boolean wasActiveAdmin = u.isAdmin() && u.active;
        applyFields(u, b);
        if (u.id.equals(me.id) && (!u.active || !u.isAdmin()))
            throw new ApiError(400, "Không thể tự khóa hoặc tự hạ quyền Admin đang đăng nhập.");
        if (wasActiveAdmin && (!u.active || !u.isAdmin()) && users.countByRoleAndActiveTrue("admin") <= 1)
            throw new ApiError(400, "Phải giữ ít nhất một Admin đang hoạt động.");
        users.save(u);
        audits.log(me.username, "update_user", u.username);
        return Map.of("ok", true);
    }

    @DeleteMapping("/users/{id}")
    public Map<String, Object> delete(@PathVariable Long id, HttpSession s) {
        User me = access.admin(s);
        User u = find(id);
        if (u.id.equals(me.id)) throw new ApiError(400, "Không thể xóa tài khoản đang đăng nhập.");
        if (u.isAdmin() && u.active && users.countByRoleAndActiveTrue("admin") <= 1)
            throw new ApiError(400, "Không thể xóa Admin hoạt động cuối cùng.");
        users.delete(u);
        audits.log(me.username, "delete_user", u.username);
        return Map.of("ok", true);
    }

    @PostMapping("/users/{id}/reset-password")
    public Map<String, Object> resetPassword(@PathVariable Long id, @RequestBody Map<String, Object> b, HttpSession s) {
        User me = access.admin(s);
        if (id.equals(me.id)) throw new ApiError(400, "Dùng mục Đổi mật khẩu cho tài khoản của bạn.");
        User u = find(id);
        u.passwordHash = encoder.encode(Json.text(b, "password", 10, 128));
        u.mustChange = true;
        users.save(u);
        audits.log(me.username, "reset_password", u.username);
        return Map.of("ok", true);
    }

    /** Gan danh sach thiet bi user duoc xem. Body: ["esp32-tang1", ...] */
    @PutMapping("/users/{id}/devices")
    public Map<String, Object> assignDevices(@PathVariable Long id, @RequestBody List<String> deviceIds, HttpSession s) {
        User me = access.admin(s);
        User u = find(id);
        for (String d : deviceIds) {
            if (!devices.existsById(d)) throw new ApiError(400, "Không có thiết bị: " + d);
        }
        u.devices = new HashSet<>(deviceIds);
        users.save(u);
        audits.log(me.username, "assign_devices", u.username);
        return Map.of("ok", true);
    }

    @GetMapping("/audit")
    public Map<String, Object> audit(HttpSession s) {
        access.admin(s);
        List<Map<String, Object>> rows = new ArrayList<>();
        for (AuditLog a : audits.findTop100ByOrderByIdDesc()) {
            Map<String, Object> r = new HashMap<>();
            r.put("occurred", Json.sec(a.occurredAt));
            r.put("actor", a.actor);
            r.put("action", a.action);
            r.put("target", a.target);
            rows.add(r);
        }
        return Map.of("rows", rows);
    }

    private User find(Long id) {
        return users.findById(id).orElseThrow(() -> new ApiError(404, "Không tìm thấy tài khoản."));
    }

    /** Doc cac truong chung khi tao/sua user. */
    private void applyFields(User u, Map<String, Object> b) {
        u.fullName = Json.text(b, "full_name", 1, 80).trim();
        String role = String.valueOf(b.getOrDefault("role", "user"));
        if (!role.equals("admin") && !role.equals("user")) throw new ApiError(400, "Vai trò không hợp lệ.");
        u.role = role;
        if (!(b.getOrDefault("active", true) instanceof Boolean active)) throw new ApiError(400, "Trạng thái không hợp lệ.");
        u.active = active;
        List<String> perms = new ArrayList<>();
        for (Object p : (List<?>) b.getOrDefault("permissions", List.of())) {
            if (!User.ALL_PERMISSIONS.contains(p)) throw new ApiError(400, "Quyền không hợp lệ.");
            if (!perms.contains(p)) perms.add((String) p);
        }
        u.permissions = String.join(",", perms);
    }
}
