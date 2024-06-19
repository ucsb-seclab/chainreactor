; in this scenario, bob can gain privesc
; by making bash suid and then spawning a shell
(define (problem escalate-shell-via-new-suid-executable)
  (:domain micronix)
  (:objects
    alice bob - user
    alice_group bob_group - group
    chmod bash - executable
    process - process
    data - data
    location - local
  )

  (:init
    (CAP_change_permission chmod)
    (system_executable chmod)
    (executable_does_not_drop_privileges chmod)
    (suid_executable chmod)
    (file_owner chmod alice alice_group)
    
    (CAP_shell bash)
    (system_executable bash)
    (executable_does_not_drop_privileges bash)
    (file_owner bash alice alice_group)
    
    (user_group alice alice_group)
    (user_group bob bob_group)
    
    (controlled_user bob)
  )

  (:goal (controlled_user alice))
)