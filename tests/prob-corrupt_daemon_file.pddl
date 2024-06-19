; in this scenario, we want to corrupt a service file
; such that we can inject a different command
; (in our case a shell) and then control a different user
; TODO: for now we DO NOT check who is calling the service
; as we assume it's called by root or, in any case, a different
; user from the controlled one
(define (problem write-file)
  (:domain micronix)
  (:objects
    alice bob - user
    alice_g bob_g - group
    writer - executable
    process - process
    data - data
    location - local
    daemon_file - file
  )

  (:init
    (CAP_write_file writer)
    (system_executable writer)

    (user_group alice alice_g)
    (user_group bob bob_g)

    (daemon_file daemon_file)
    (file_owner daemon_file alice alice_g)

    (user_file_permission bob daemon_file FS_WRITE)
        
    (controlled_user bob)
  )

  (:goal (controlled_user alice))
)