package com.firewatch.api;

import com.firewatch.model.Device;
import com.firewatch.model.User;
import java.time.Instant;
import java.util.*;

/** Ham tien ich: doc du lieu vao va tao JSON tra ve (ten snake_case khop frontend). */
public final class Json {
    private Json() {}

    /** Lay chuoi tu JSON va kiem tra do dai. */
    public static String text(Map<String, Object> b, String key, int min, int max) {
        if (!(b.get(key) instanceof String v) || v.length() < min || v.length() > max)
            throw new ApiError(400, "Trường '" + key + "' cần từ " + min + " đến " + max + " ký tự.");
        return v;
    }

    /** Thoi gian dang so giay (frontend dung ts * 1000). */
    public static Double sec(Instant t) {
        return t == null ? null : t.toEpochMilli() / 1000.0;
    }

    public static Map<String, Object> user(User u) {
        Map<String, Object> r = new HashMap<>();
        r.put("id", u.id);
        r.put("username", u.username);
        r.put("full_name", u.fullName);
        r.put("role", u.role);
        r.put("permissions", u.permissionList());
        r.put("active", u.active);
        r.put("must_change", u.mustChange);
        r.put("devices", new TreeSet<>(u.devices));
        return r;
    }

    /** Trang thai ket noi cua thiet bi: online / stale (qua 15s khong co du lieu) / offline. */
    public static Map<String, Object> state(Device d) {
        Double age = d.lastSeen == null ? null : Math.max(0, (System.currentTimeMillis() - d.lastSeen.toEpochMilli()) / 1000.0);
        boolean fresh = d.online && age != null && age <= 15;
        Map<String, Object> r = new HashMap<>();
        r.put("device", d.deviceId);
        r.put("last_seen", sec(d.lastSeen));
        r.put("age_seconds", age == null ? null : Math.round(age * 10) / 10.0);
        r.put("fresh", fresh);
        r.put("connection", !d.online ? "offline" : fresh ? "online" : "stale");
        return r;
    }
}
