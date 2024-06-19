(define (problem add-permission)
  (:domain micronix)
  (:objects
    alice bob - user
    file - file
    chown - executable
    process - process
    data - data
    group - group
  )

  (:init
    (CAP_change_file_owner chown)
    (system_executable chown)

    (user_is_admin alice)
    (file_owner file alice group)
    (user_group alice group)
    (user_group bob group)
    
    (controlled_user alice)
  )

  (:goal (file_owner file bob group))
)