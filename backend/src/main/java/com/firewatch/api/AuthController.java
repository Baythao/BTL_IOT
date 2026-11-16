package com.firewatch.api;

import com.firewatch.model.Repos;
import com.firewatch.model.User;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/** Dang nhap, dang xuat, phien, doi mat khau. */
@RestController
@RequestMapping("/api")
public class AuthController {
    private final Repos.Users users;
    private final Repos.Audits audits;
    private final PasswordEncoder encoder;
    private final Access access;
    private final String dummyHash;                                  // chong do ten dang nhap qua thoi gian
    private final Map<String, List<Long>> loginFailures = new ConcurrentHashMap<>();

    public AuthController(Repos.Users users, Repos.Audits audits, PasswordEncoder encoder, Access access) {
        this.users = users;
        this.audits = audits;
        this.encoder = encoder;
        this.access = access;
        this.dummyHash = encoder.encode(UUID.randomUUID().toString());
    }

    @GetMapping("/session")
    public Map<String, Object> session(HttpSession s, CsrfToken csrf) {
        User u = access.findUser(s);
        String dev = u == null ? null : access.defaultDevice(u);
        Map<String, Object> r = new HashMap<>();
        r.put("user", u == null ? null : Json.user(u));
        r.put("csrf", csrf.getToken());
        r.put("device", dev == null ? "FireWatch" : dev);
        return r;
    }

    @PostMapping("/login")
    public Map<String, Object> login(@RequestBody Map<String, Object> b, HttpServletRequest req, CsrfToken csrf) {
        String name = Json.text(b, "username", 0, 64).trim().toLowerCase();
        String pass = Json.text(b, "password", 0, 128);

        // Sai qua 8 lan trong 15 phut -> khoa tam (theo IP + ten dang nhap)
        String key = req.getRemoteAddr() + "|" + name;
        long now = System.currentTimeMillis();
        if (loginFailures.size() > 10000) loginFailures.clear();
        List<Long> fails = loginFailures.computeIfAbsent(key, k -> new ArrayList<>());
        synchronized (fails) {
            fails.removeIf(t -> t < now - 15 * 60 * 1000);
            if (fails.size() >= 8) throw new ApiError(429, "Đăng nhập sai quá nhiều lần. Thử lại sau 15 phút.");
        }

        User u = users.findByUsername(name).orElse(null);
        boolean ok = encoder.matches(pass, u == null ? dummyHash : u.passwordHash);
        if (u == null || !ok || !u.active) {
            synchronized (fails) { fails.add(now); }
            throw new ApiError(401, "Tên đăng nhập hoặc mật khẩu không đúng, hoặc tài khoản đã bị khóa.");
        }
        loginFailures.remove(key);

        req.getSession();
        req.changeSessionId();                          // chong session fixation
        req.getSession().setAttribute("uid", u.id);
        audits.log(u.username, "login", u.username);
        return Map.of("user", Json.user(u), "csrf", csrf.getToken());
    }

    @PostMapping("/logout")
    public Map<String, Object> logout(HttpSession s) {
        s.invalidate();
        return Map.of("ok", true);
    }

    @PostMapping("/password")
    public Map<String, Object> changePassword(@RequestBody Map<String, Object> b, HttpSession s) {
        User u = access.loggedIn(s, true);
        String oldPass = Json.text(b, "current", 0, 128);
        String newPass = Json.text(b, "new", 10, 128);
        if (!encoder.matches(oldPass, u.passwordHash)) throw new ApiError(400, "Mật khẩu hiện tại không đúng.");
        if (oldPass.equals(newPass)) throw new ApiError(400, "Mật khẩu mới phải khác mật khẩu hiện tại.");
        u.passwordHash = encoder.encode(newPass);
        u.mustChange = false;
        users.save(u);
        audits.log(u.username, "change_password", u.username);
        return Map.of("ok", true);
    }
}
