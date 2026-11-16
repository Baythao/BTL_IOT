package com.firewatch.api;

import com.firewatch.model.Device;
import com.firewatch.model.Repos;
import com.firewatch.model.User;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.*;

/** Admin: vong doi thiet bi PENDING -> ACTIVE <-> DISABLED -> RETIRED. */
@RestController
@RequestMapping("/api/admin/devices")
public class AdminDeviceController {
    private final Repos.Devices devices;
    private final Repos.Audits audits;
    private final Access access;

    public AdminDeviceController(Repos.Devices devices, Repos.Audits audits, Access access) {
        this.devices = devices;
        this.audits = audits;
        this.access = access;
    }

    @GetMapping
    public Map<String, Object> list(HttpSession s) {
        access.admin(s);
        List<Map<String, Object>> list = new ArrayList<>();
        for (Device d : devices.findAllByOrderByDeviceId()) {
            Map<String, Object> r = Json.state(d);
            r.put("name", d.name);
            r.put("location", d.location);
            r.put("status", d.status);
            r.put("created_at", Json.sec(d.createdAt));
            list.add(r);
        }
        return Map.of("devices", list);
    }

    /** Dang ky thiet bi moi, bat dau o trang thai PENDING. */
    @PostMapping
    public ResponseEntity<Map<String, Object>> create(@RequestBody Map<String, Object> b, HttpSession s) {
        User me = access.admin(s);
        Device d = new Device();
        d.deviceId = Json.text(b, "device_id", 1, 40);
        if (!d.deviceId.matches("[A-Za-z0-9_-]+")) throw new ApiError(400, "Mã thiết bị chỉ gồm chữ, số, dấu _ -");
        if (devices.existsById(d.deviceId)) throw new ApiError(409, "Mã thiết bị đã tồn tại.");
        d.name = Json.text(b, "name", 1, 80);
        d.location = b.get("location") == null ? null : Json.text(b, "location", 0, 120);
        devices.save(d);
        audits.log(me.username, "create_device", d.deviceId);
        return ResponseEntity.status(201).body(Map.of("device_id", d.deviceId));
    }

    /** Sua ten/vi tri hoac doi trang thai (kich hoat, vo hieu, ngung su dung). */
    @PatchMapping("/{id}")
    public Map<String, Object> update(@PathVariable String id, @RequestBody Map<String, Object> b, HttpSession s) {
        User me = access.admin(s);
        Device d = devices.findById(id).orElseThrow(() -> new ApiError(404, "Không tìm thấy thiết bị."));
        if (b.containsKey("name")) d.name = Json.text(b, "name", 1, 80);
        if (b.containsKey("location")) d.location = Json.text(b, "location", 0, 120);
        if (b.containsKey("status")) {
            String to = Json.text(b, "status", 1, 10).toUpperCase();
            if (!Device.canMove(d.status, to))
                throw new ApiError(400, "Không thể chuyển từ " + d.status + " sang " + to + ".");
            d.status = to;
            if (!to.equals("ACTIVE")) d.online = false;
        }
        devices.save(d);
        audits.log(me.username, "update_device", d.deviceId + " -> " + d.status);
        return Map.of("ok", true);
    }
}
