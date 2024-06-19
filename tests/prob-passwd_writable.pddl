; in this scenario, bob overwrites alice's entry in /etc/passwd to a known password hash
(define (problem passwd_writable)
  (:domain micronix)
  (:objects
    alice bob - user
    alice_g bob_g - group
    etc_passwd - file
  )

  (:init
    (controlled_user bob)
    (user_group alice alice_g)
    (user_group bob bob_g)
    
    (file_purpose etc_passwd SYSFILE_PASSWD)
    (user_file_permission bob etc_passwd FS_WRITE)
  )

  (:goal (controlled_user alice))
)