package com.firewatch;

import com.firewatch.model.Repos;
import com.firewatch.model.User;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import java.util.TimeZone;

@SpringBootApplication
@EnableJpaRepositories(considerNestedRepositories = true)
public class App {

    public static void main(String[] args) {
        // PostgreSQL/Supabase khong nhan ten mui gio cu "Asia/Saigon" -> dung UTC (timestamptz van dung gio)
        TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
        SpringApplication.run(App.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    /**
     * Spring Security chi lo: CSRF + header bao mat.
     * Dang nhap va phan quyen viet thang trong ApiController cho de doc.
     */
    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        HttpSessionCsrfTokenRepository csrfRepo = new HttpSessionCsrfTokenRepository();
        csrfRepo.setHeaderName("X-CSRF-Token");   // frontend gui token qua header nay

        http.csrf(c -> c.csrfTokenRepository(csrfRepo)
                        .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler()))
            .authorizeHttpRequests(a -> a.anyRequest().permitAll())
            .exceptionHandling(e -> e.accessDeniedHandler((req, res, ex) -> {
                res.setStatus(403);
                res.setContentType("application/json;charset=UTF-8");
                res.getWriter().write("{\"error\":\"Phiên không hợp lệ. Tải lại trang rồi thử lại.\"}");
            }))
            .headers(h -> h.contentSecurityPolicy(c -> c.policyDirectives(
                "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")))
            .formLogin(f -> f.disable())
            .httpBasic(b -> b.disable())
            .logout(l -> l.disable());
        return http.build();
    }

    /** Tao Admin dau tien neu bang users dang trong. */
    @Bean
    CommandLineRunner createFirstAdmin(Repos.Users users, Repos.Audits audits, PasswordEncoder encoder,
                                       @Value("${admin.user}") String name,
                                       @Value("${admin.pass}") String pass) {
        return args -> {
            if (users.count() > 0) return;
            if (pass.length() < 10) {
                System.out.println(">>> Chua co user nao. Dat ADMIN_PASS (>= 10 ky tu) trong .env roi chay lai.");
                return;
            }
            User admin = new User();
            admin.username = name.trim().toLowerCase();
            admin.fullName = "Quản trị viên";
            admin.passwordHash = encoder.encode(pass);
            admin.role = "admin";
            users.save(admin);
            audits.log("local-setup", "create_first_admin", admin.username);
            System.out.println(">>> Da tao Admin: " + admin.username + ". Nen xoa ADMIN_PASS khoi .env.");
        };
    }
}
