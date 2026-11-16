package com.firewatch.model;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.*;

/** Tat ca repository gom trong mot file cho gon. */
public class Repos {

    public interface Users extends JpaRepository<User, Long> {
        Optional<User> findByUsername(String username);
        long countByRoleAndActiveTrue(String role);
    }

    public interface Devices extends JpaRepository<Device, String> {
        List<Device> findAllByOrderByDeviceId();

        // Chi cap nhat cot trang thai, khong ghi de status do Admin vua doi
        @Modifying @Transactional
        @Query(value = "update devices set last_payload = cast(?2 as jsonb), last_seen = now(), online = true"
                     + " where device_id = ?1 and status = 'ACTIVE'", nativeQuery = true)
        int saveState(String deviceId, String payload);

        @Modifying @Transactional
        @Query(value = "update devices set online = ?2 where device_id = ?1", nativeQuery = true)
        int saveOnline(String deviceId, boolean online);
    }

    public interface Events extends JpaRepository<AlarmEvent, String> {
        List<AlarmEvent> findTop100ByDeviceIdAndReceivedAtBeforeOrderByReceivedAtDesc(String deviceId, Instant before);
    }

    public interface Audits extends JpaRepository<AuditLog, Long> {
        List<AuditLog> findTop100ByOrderByIdDesc();

        default void log(String actor, String action, String target) {
            AuditLog a = new AuditLog();
            a.actor = actor;
            a.action = action;
            a.target = target;
            save(a);
        }
    }
}
